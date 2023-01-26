# review-reminder.py
#  python script to notify individuals in teams if they have outstanding merge requests requiring their review
# prerequisites:
#  each gitlab user should have their "public email" set to their teams email
# usage:
#  GITLAB_API_URL=".../api/v4" \
#  GITLAB_PRIVATE_TOKEN="..." \
#  GITLAB_PROJECTS="myproject,myproject2" \
#  TEAMS_WEBHOOK_URL="..." \
#  python3 review-reminder.py
# optional:
#  USER_EMAILS="{\"username\":\"email\"}" : Useful if a user is unable to set their "public email" for some reason

# TODO: Handle MRs that have unaddressed threads, and notify the author instead

import os
import json
import requests
from datetime import datetime

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
    projects = response.json()
    return projects[0]["id"] if projects else None

def get_merge_requests(project_id):
    url = f"{GITLAB_API_URL}/projects/{project_id}/merge_requests"
    response = requests.get(url, params = {"per_page": "100", "state": "opened"}, headers = headers)
    return response.json()

def get_reviewers(reviewers):
    return [reviewer["id"] for reviewer in reviewers]

def request_approvers(project_id, mr_id):
    url = f"{GITLAB_API_URL}/projects/{project_id}/merge_requests/{mr_id}/approvals"
    response = requests.get(url, headers = headers)
    return get_approvers(response.json())

def get_approvers(approvers):
    return [approver["user"]["id"] for approver in approvers["approved_by"]]

def get_user_info(user_id):
    url = f"{GITLAB_API_URL}/users/{user_id}"
    response = requests.get(url, headers = headers)
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

for project in GITLAB_PROJECTS.split(','):
    project_id = get_project_id(project)
    merge_requests = filter(lambda mr: not mr['draft'], get_merge_requests(project_id))

    project_body = []
    for merge_request in merge_requests:
        mr_id = merge_request["iid"]

        reviewers = get_reviewers(merge_request["reviewers"])
        approvers = request_approvers(project_id, mr_id)
        pending = set(reviewers) - set(approvers)

        if len(pending) > 0:
            mr_title = merge_request["title"]
            mr_url = merge_request["web_url"]
            title = f"[{mr_title}]({mr_url})"
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
