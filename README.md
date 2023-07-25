# gitlab-teams-review-reminder
A script to notify individuals in Microsoft Teams about outstanding merge requests assigned to them in GitLab

## Prerequisites:
 - Each GitLab user should have their "public email" set to their Teams email
   - This is how gitlab-teams-review-reminder is able to find their Teams account

## Required Environment Variables:
- GITLAB_API_URL="YOUR_GITLAB_URL/api/v4"
  - Your GitLab API url
- GITLAB_PRIVATE_TOKEN="YOUR_GITLAB_TOKEN"
  - Your GitLab API token
- GITLAB_PROJECTS="PROJECT_1,PROJECT_2"
  - Comma separated list of your GitLab projects that you want to be reminded about
- TEAMS_WEBHOOK_URL="YOUR_TEAMS_WEBHOOK_URL"
  - Your Microsoft Teams webhook url
## Optional Environment Variables:
- USER_EMAILS="{\"username\":\"email\"}"
  - Useful if a user is unable to set their "public email" for some reason

## Executing
python3 review-reminder.py
