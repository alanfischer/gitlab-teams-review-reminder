# review-reminder.py
# python script to notify individuals in teams if they have outstanding merge requests requiring their review
# prerequisites:
# each gitlab user should have their "public email" set to their teams email
# usage:
# GITLAB_API_URL=".../api/v4" \
# GITLAB_PRIVATE_TOKEN="..." \
# GITLAB_PROJECTS="myproject,myproject2" \
# TEAMS_WEBHOOK_URL="..." \
# python3 review-reminder.py
# optional:
# USER_EMAILS="{\"username\":\"email\"}" : Useful if a user is unable to set their "public email" for some reason

import os
import json
import requests
from datetime import datetime, timedelta

GITLAB_API_URL = os.getenv("GITLAB_API_URL")
GITLAB_PRIVATE_TOKEN = os.getenv("GITLAB_PRIVATE_TOKEN")
GITLAB_PROJECTS = os.getenv("GITLAB_PROJECTS")
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL")
USER_EMAILS = os.getenv("USER_EMAILS")

headers = {"PRIVATE-TOKEN": GITLAB_PRIVATE_TOKEN}
user_emails = json.loads(USER_EMAILS) if USER_EMAILS else {}

def get_project_id(project):
    url = f"{GITLAB_API_URL}/search"
    response = requests.get(url, params = {"scope": "projects", "search": project}, headers = headers)
    if not response.ok:
        raise Exception(response.json())
    projects = response.json()
    return projects[0]["id"] if projects else None

def get_merge_requests(project_id):
    url = f"{GITLAB_API_URL}/projects/{project_id}/merge_requests"
    response = requests.get(url, params = {"per_page": "100", "state": "opened"}, headers = headers)
    if not response.ok:
        raise Exception(response.json())
    return response.json()

def get_mr_discussions(project_id, mr_id):
    url = f"{GITLAB_API_URL}/projects/{project_id}/merge_requests/{mr_id}/discussions"
    response = requests.get(url, headers=headers)
    if not response.ok:
        raise Exception(response.json())
    return response.json()

def get_reviewers(reviewers):
    return [reviewer["id"] for reviewer in reviewers]

def request_approvers(project_id, mr_id):
    url = f"{GITLAB_API_URL}/projects/{project_id}/merge_requests/{mr_id}/approvals"
    response = requests.get(url, headers = headers)
    if not response.ok:
        raise Exception(response.json())
    return get_approvers(response.json())

def get_approvers(approvers):
    return [approver["user"]["id"] for approver in approvers["approved_by"]]

def get_user_info(user_id):
    url = f"{GITLAB_API_URL}/users/{user_id}"
    response = requests.get(url, headers = headers)
    if not response.ok:
        raise Exception(response.json())
    user_data = response.json()

    username = user_data["username"]
    name = user_data["name"]
    email = user_data["public_email"]

    if not name:
        name = username

    if not email:
        email = user_emails.get(username)

    return {
        "username": username,
        "name": name,
        "email": email
    }

def make_text(text, bold = False, separator = False):
    return [{
        "type": "TextBlock",
        "text": text,
        "separator": separator,
        "weight": "bolder" if bold else "default"
    }]

def make_mentions(user_ids):
    users = [get_user_info(id) for id in user_ids]
    users = [user for user in users if user["email"]]

    mentions = ' '.join(["<at>" + user["name"] + "</at>" for user in users])
    entities = []
    for user in users:
        entities.append({
            "type": "mention",
            "text": "<at>" + user["name"] + "</at>",
            "mentioned": {
                "id": user["email"],
                "name": user["name"]
            }
        })

    return [{
        "type": "TextBlock",
        "text": mentions
    }], entities

def make_message(body, entities):
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "body": body,
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "version": "1.0",
                "msteams": {
                    "entities": entities,
                    "width": "Full"
                }
            }
        }]
    }

notified_mrs = set()
notified_people = set()
body = []
entities = []

text = "Happy " + datetime.now().strftime('%A') + " Everyone!"
body = body + make_text(text)
text = "Here are the Merge Requests needing review..."
body = body + make_text(text)

if GITLAB_PROJECTS:
    for project in GITLAB_PROJECTS.split(','):
        project_id = get_project_id(project)
        merge_requests = filter(lambda mr: not mr['draft'], get_merge_requests(project_id))

        project_body = []
        for merge_request in merge_requests:
            mr_id = merge_request["iid"]

            # Fetching discussions for the MR
            discussions = get_mr_discussions(project_id, mr_id)
            # Find authors of unresolved discussion notes
            authors_unresolved_discussions = set()
            for discussion in discussions:
                for note in discussion['notes']:
                    if 'resolved' in note and not note['resolved']:
                        authors_unresolved_discussions.add(note['author']['id'])

            reviewers = get_reviewers(merge_request["reviewers"])
            approvers = request_approvers(project_id, mr_id)
            pending = set(reviewers) - set(approvers)

            if len(authors_unresolved_discussions) > 0 or len(pending) == 0:
                # Exclude authors of unresolved discussions
                pending -= authors_unresolved_discussions
                # Notify author if any unresolved discussions, or no one to notify
                pending.update(set([merge_request['author']['id']]))

            updated_at = merge_request['updated_at']
            updated_date = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%S.%fZ")
            current_date = datetime.utcnow()

            # Don't count weekends
            dates = (updated_date + timedelta(idx + 1) for idx in range((current_date - updated_date).days))
            stale_days = sum(1 for day in dates if day.weekday() < 5)

            stale = ""
            if stale_days > 2:
                stale = f" {stale_days} days old"

            mr_title = merge_request["title"]
            mr_url = merge_request["web_url"]
            title = f"[{mr_title}]({mr_url})" + stale
            title = make_text(title, bold = True)

            mention_parts, mention_entities = make_mentions(pending)

            project_body = project_body + title + mention_parts
            entities = entities + mention_entities

            notified_mrs.add(mr_id)
            notified_people.update(pending)

        if len(project_body) > 0:
            body = body + make_text("") + make_text(project, bold = True) + [
                {
                    'type': 'ColumnSet',
                    'columns': [
                        {
                            'type': 'Column',
                            'width': 'auto',
                            'items': [
                                {
                                    'type': 'TextBlock',
                                    'text': ''
                                }
                            ]
                        },
                        {
                            'type': 'Column',
                            'width': 'stretch',
                            'separator': True,
                            'items': project_body
                        }
                    ]
                }
            ]

if len(notified_people) > 0:
    message = make_message(body, entities)
    print(json.dumps(message, indent=2))
    response = requests.post(TEAMS_WEBHOOK_URL, json = message)

print(f"Notified {len(notified_people)} people about {len(notified_mrs)} MRs")
