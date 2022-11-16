#! /usr/bin/python3
import git
import requests
import re
import os
import time
import logging

'''
A script to parse JFrog YAML config files to ensure that the usernames are properly documented with comments:
- username            # Full, Name - Em@il
'''


##### VARIABLES
# Authentication Credentials
username = os.environ['username']
token = os.environ['GERRIT']
# Jfrog config repository Git information
branch = "branch"
config_repository = "config_repository"
# Cloning Jfrog Config Repository
config_repository_url = f"https://{username}:{token}@gerrit.com/a/{config_repository}"
git.Repo.clone_from(config_repository_url, config_repository, branch=branch)
# All files and folders in Jfrog config repository
config_repository_content = os.listdir(config_repository)
# Only Folders in Jfrog config repository
config_repository_projects = [os.path.join(config_repository, directory) for directory in config_repository_content if os.path.isfile(os.path.join(config_repository, directory)) == False]
# RegEx patterns
regex_usernames_pattern = "(?<=userNames:\n)((.|\n)*?)(?=(\s{4}-\sstate:))"
regex_name_pattern = "(?<=<br>name:\s)(.*)(?=<br>company)"
regex_email_pattern = "(?<=<br>email:\s)(.*)(?=<br>)"
# Dictionaries to store usernames informations: {'username':'comment'}
all_users_db = {} 
project_users_db = {}
# Other
config_filename = "jfrog-service.yaml"

for project in config_repository_projects:
    print(f'###################### PROJECT: {project.replace(f"{config_repository}","")} ######################')
    config_file = os.path.join(project, config_filename)
    try:
        ##### PARSING THE CONFIG FILE AND STORING THE USERNAMES
        # Finding all usernames in the JFrog config file using regex
        with open(config_file, "r") as f:
            all_users = re.findall(regex_usernames_pattern, f.read())
            # Tranforming usernames into Python dictionary and syncing the previous information we have (all_users_db) with this project (project_users_db):
            for user_groups in all_users:
                # user_groups[0] contians the RegEx group that has the usernames separated by \n.
                for user in list(user_groups)[0].split('\n'):
                    # In case there was an empty line in the user names, we skip it
                    if user == '' or user == ' ':
                        continue
                    # Regex pattern to match all trailing and leading spaces including the yaml hyphen
                    regex_all_spaces_pattern = "(^(\s*))|(\s*)$"
                    # We store the cleaned username after isolating the comment part, if any
                    cleaned_username = re.sub(regex_all_spaces_pattern, "", user.split("#")[0])
                    # In case we have not processes this username before in different projects, we add it to both dictionaries (project and all users) with the existing comment
                    if cleaned_username not in all_users_db.keys():
                        try:
                            project_users_db[cleaned_username] = user.split("#")[1].strip()
                            all_users_db[cleaned_username] = user.split("#")[1].strip()
                        # In case there is no comment in the config file (KeyError exception), we add an empty comment.
                        except:
                            project_users_db[cleaned_username] = ""
                            all_users_db[cleaned_username] = ""
                    # In case this username has been processed before, we just sync the username with the project dictionary from the all users dictionary 
                    else:
                        project_users_db[cleaned_username] = all_users_db[cleaned_username]

            ##### FETCHING THE MISSING INFROMATION ABOUT THE USERS WE HAVE
            # Sending an HTTP request for each user
            for username in project_users_db.keys():
                # Only in case an email, full name or both are missing:
                if '@' not in project_users_db[username] or ',' not in project_users_db[username]:
                    url = "" #Redacted: web app endpoint that resolves ldap user names and return their information.
                    payload = f'UserEmail={username}'
                    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
                    # Using timeout of 10 seconds because the tool is very old and unpredictable and only works on the 2-3 request
                    timeout = time.time() + 10
                    # HTTP Request
                    response = (requests.request("POST", url, headers=headers, data=payload)).text
                    # We keep sending requests until we either get a legit response or we time out
                    while "company" not in response and time.time() < timeout:
                        if "No AD entry found" in response:
                            project_users_db[username] = "# username Not Found"
                            all_users_db[username] = "# username Not Found"
                            break
                        response = (requests.request("POST", url, headers=headers, data=payload)).text
                    # At this point the user exists, we will apply RegEx patterns to extract the name and email
                    name = re.findall(regex_name_pattern, response)
                    email = re.findall(regex_email_pattern, response)
                    # If we have matches for both name and email, we update both dictionaries
                    if len(name) >= 1 and len(email) >= 1:
                        project_users_db[username] = "# " + name[0] + " - " + email[0]
                        all_users_db[username] = "# " + name[0] + " - " + email[0]
                    # We need to handle special type of users (Non-interactive user)
                    elif "sid" in username or "gid" in username:
                        project_users_db[username] = "# Non-interactive user"
                        all_users_db[username] = "# Non-interactive user"

            ##### WRITING DOWN THE INFORMATION WE GOT TO THE CONFIG FILES
            with open(config_file, 'r') as f:
                content = f.read()
                # We parse every user in the project user dictionary
                for username in project_users_db.keys():
                    # To avoid replacing lines that match our format requirement, we will only replace occurrences that   
                    # do not match the requirement by specifically declaring each scenario
                    # Regex pattern to match only the username scenario:
                    username_only_regex = r"-\s" + username + r"\s*$"
                    # Regex pattern to match only the username and email scenario:
                    username_email_regex = r"-\s" + username + r"\s*#.*@.*$"
                    # Regex pattern to match only the username and full name scenario:
                    username_name_regex = r"-\s" + username + r"\s*#.*,.*$"
                    # Regex pattern to match only the username and a random comment scenario:
                    username_other_regex = r"-\s" + username + r"\s*#*.*$"

                    sep = " " * 12
                    # We replace each occurrence with the desired format:
                    if re.findall(username_only_regex, content, re.MULTILINE) != []:
                        content = re.sub(username_only_regex,  (username + sep + project_users_db[username]), content, 0, re.MULTILINE)
                    elif re.findall(username_email_regex, content, re.MULTILINE) != []:
                        content = re.sub(username_email_regex, (username + sep + project_users_db[username]), content, 0, re.MULTILINE)
                    elif re.findall(username_name_regex, content, re.MULTILINE) != []:
                        content = re.sub(username_name_regex,  (username + sep + project_users_db[username]), content, 0, re.MULTILINE)
                    elif re.findall(username_other_regex, content, re.MULTILINE) != []:
                        content = re.sub(username_other_regex,  (username + sep + project_users_db[username]), content, 0, re.MULTILINE)
                    logging.info(f"USER {username} WAS NOT MATCHED")

        # We write to the config file
        with open(config_file, 'w+') as f:
            f.write(content)

        ### CREATING A CHANGE (EQ TO PULL REQUEST) IN GERRIT TO MERGE THE CHANGES
        commit_msg = f'JFrog Config Changes for: {project.replace(f"{config_repository}/","")}'
        repository = git.Repo(config_repository)
        repository.git.add(project.replace(f"{config_repository}/",""))
        repository.index.commit(commit_msg)
        repository.git.push("origin", f"HEAD:refs/for/{branch}")
        print('DONE')
        # Resetting the project users dictionary
        project_users_db = {}
    
    #  Config file not found exception handling
    except FileNotFoundError:
        logging.info(f"CONFIG NOT FOUND FOR PROJECT: {project}")