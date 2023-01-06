# review-reminder.py
#  python script to notify individuals in teams if they have outstanding merge requests requiring their review
# prerequisites:
#  each gitlab user should have their "public email" set to their teams email
# usage:
#  GITLAB_API_URL=".../api/v4" \
#  GITLAB_PRIVATE_TOKEN="..." \
#  GITLAB_PROJECT="myproject" \
#  TEAMS_WEBHOOK_URL="..." \
#  python3 review-reminder.py
# optional:
#  USER_EMAILS="{\"username\":\"email\"}" : Useful if a user is unable to set their "public email" for some reason

# TODO: Handle MRs that have unaddressed threads, and notify the author instead

import os
import json
import requests

GITLAB_API_URL = os.getenv("GITLAB_API_URL")
GITLAB_PRIVATE_TOKEN = os.getenv("GITLAB_PRIVATE_TOKEN")
GITLAB_PROJECT = os.getenv("GITLAB_PROJECT")
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

    return {
        "username": username,
        "name": name,
        "email": email
    }

def get_message_parts(mr_title, mr_url, user_ids):
    message = f"[{mr_title}]({mr_url})"

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

    return {
        "body": [
            {
                "type": "TextBlock",
                "text": message
            },
            {
                "type": "TextBlock",
                "text": mentions
            }
        ],
        "entities": entities
    }

def get_message(body, entities):
    title = "Outstanding MR review requests"

    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "body": [
                    {
                        "type": "TextBlock",
                        "weight": "Bolder",
                        "text": title
                    },
                ] + body,
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "version": "1.0",
                "msteams": {
                    "entities": entities,
                    "width": "Full"
                }
            }
        }]
    }

project_id = None
merge_requests = []

if GITLAB_PROJECT:
    project_id = get_project_id(GITLAB_PROJECT)
    merge_requests = get_merge_requests(project_id)

body = []
entities = []
notified_mrs = set()
notified_people = set()

for merge_request in merge_requests:
    if merge_request["draft"]:
        continue

    mr_id = merge_request["iid"]
    mr_title = merge_request["title"]
    mr_url = merge_request["web_url"]

    reviewers = get_reviewers(merge_request["reviewers"])
    approvers = request_approvers(project_id, mr_id)
    pending = set(reviewers) - set(approvers)

    if len(pending) > 0:
        parts = get_message_parts(mr_title, mr_url, pending)
        body = body + parts["body"]
        entities = entities + parts["entities"]

        notified_mrs.add(mr_id)
        notified_people.update(pending)

if body:
    message = get_message(body, entities)
    response = requests.post(TEAMS_WEBHOOK_URL, json = message)

print(f"Notified {len(notified_people)} people about {len(notified_mrs)} MRs")
