import requests
import socket
import json
import logging
import os
import six
import time

if six.PY2:
  import urllib
else:
  from urllib.parse import urlencode, quote_plus

dsm_host = ""
dsm_port = "5001"
user_name = ""
password = ""
https = True
s = requests.Session()

def update_images(headers, cookies, syno_server_url, containers):
    """Update Docker Images"""
    def update_image(container_image):
        """Update Docker Image"""
        payload = {
            "api": "SYNO.Docker.Image",
            "method": "pull_start",
            "version": "1",
            "tag": "latest",
            "repository": str(container_image)
        }

        result = s.post("{}/webapi/entry.cgi".format(syno_server_url), cookies=cookies, data=payload,
                        headers=headers, verify=False)
        task_id = result.json()["data"]["task_id"]
        while(True):
            time.sleep(2)
            payload = {
                "extra_group_tasks": "[\"admin\",\"user\"]",
                "task_id_prefix": "\"SYNO_DOCKER_IMAGE_PULL\"",
                "api": "SYNO.Entry.Request.Polling",
                "method": "list",
                "version": "1"
            }
            response = s.post("{}/webapi/entry.cgi".format(syno_server_url), cookies=cookies, data=payload,
                            headers=headers, verify=False)
            if response.json()["data"].get("admin") or response.json()["data"].get("user"):
                logging.info("Updated Docker image: %s", container_image)
                break
            else:
                pass

        container_downloaded = False
        for k in response.json()["data"].keys():
            try:
                if task_id in response.json()["data"].get(k):
                    container_downloaded = True
                    break
            except (TypeError):
                pass
        return container_downloaded

    updated_images = []
    for container in containers:
        container_downloaded = update_image(container.get("image"))
        if container_downloaded:
            updated_images.append({
                "name": container.get("name"),
                "image": container.get("image"),
                "status": container.get("status"),
            })
        else:
            logging.error("Failed to update container: %s", container.get("name"))
    return updated_images

def docker_images(headers, cookies, syno_server_url):
    """Pull Docker Image Names"""

    payload = {
        "api": "SYNO.Docker.Container",
        "method": "list",
        "version": "1",
        "limit": "-1",
        "offset": "0",
        "type": "all"
    }
    result = s.post("{}/webapi/entry.cgi".format(syno_server_url), cookies=cookies, data=payload,
                    headers=headers, verify=False)
    containers = []
    for container in result.json()["data"].get("containers", []):
        logging.info("Adding container to update list: %s", container.get("name"))
        containers.append({
            "name": container.get("name"),
            "image": container.get("image"),
            "status": container.get("status"),
        })
    return containers

def stop_container(headers, cookies, syno_server_url, container):
    """Stop Docker Container"""
    payload = {
        "name": "\"{}\"".format(container.get('name')),
        "api": "SYNO.Docker.Container",
        "method": "stop",
        "version": "1",
    }

    response = s.post("{}/webapi/entry.cgi".format(syno_server_url), cookies=cookies, data=payload,
                    headers=headers, verify=False)
    if response.json()["success"]:
        return True
    else:
        return False

def clear_container(headers, cookies, syno_server_url, container):
    """Clear Docker Container"""
    payload = {
        "name": "\"{}\"".format(container.get('name')),
        "api": "SYNO.Docker.Container",
        "preserve_profile": "true",
        "force": "false",
        "method": "delete",
        "version": "1",
    }

    response = s.post("{}/webapi/entry.cgi".format(syno_server_url), cookies=cookies, data=payload,
                    headers=headers, verify=False)
    if response.json()["success"]:
        return True
    else:
        return False

def start_container(headers, cookies, syno_server_url, container):
    """Start Docker Container"""
    payload = {
        "name": "\"{}\"".format(container.get('name')),
        "api": "SYNO.Docker.Container",
        "method": "start",
        "version": "1",
    }

    response = s.post("{}/webapi/entry.cgi".format(syno_server_url), cookies=cookies, data=payload,
                    headers=headers, verify=False)
    if response.json()["success"]:
        return True
    else:
        return False
def main(dsm_host, dsm_port, user_name, password, https=None):
    logging.getLogger().addHandler(logging.StreamHandler())
    logging.getLogger().setLevel(logging.INFO)
    params = {
        "account": user_name,
        "passwd": password,
        "enable_syno_token": "yes",
        "enable_device_token": "no",
        "device_name": socket.gethostname(),
        "format": "sid",
        "api": "SYNO.API.Auth",
        "version": "6",
        "method": "login"
    }


    if https:
        syno_server_url = "https://{}:{}".format(dsm_host, dsm_port)
    else:
        syno_server_url = "http://{}:{}".format(dsm_host, dsm_port)

    requests.packages.urllib3.disable_warnings()  # Disable SSL Warnings
    if six.PY2:
        encoded_uri = urllib.urlencode(params) # Python2
    else:
        encoded_uri = urlencode(params, quote_via=quote_plus) #Python3
    auth_url = "{}/webapi/auth.cgi?{}".format(syno_server_url, encoded_uri)
    response = s.get(auth_url, verify=False)
    if response.json().get("success", False):
        logging.info("Logged into DSM Successfully")
        sid = response.json()["data"]["sid"]
        SynoToken = response.json()["data"]["synotoken"]

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-SYNO-TOKEN": SynoToken,
        }

        cookies = {
            "id": sid,
        }

        containers = docker_images(headers, cookies, syno_server_url)
        if containers:
            updated_images = update_images(headers, cookies, syno_server_url, containers)
            error = False
            for container in updated_images:
                if stop_container(headers, cookies, syno_server_url, container):
                    logging.info("Stopped Container: %s", container.get("name"))
                    time.sleep(2)
                    if stop_container(headers, cookies, syno_server_url, container):
                        logging.info("Cleared Container: %s", container.get("name"))
                        time.sleep(2)
                        if start_container(headers, cookies, syno_server_url, container):
                            logging.info("Started Container: %s", container.get("name"))
                            time.sleep(2)
                        else:
                            logging.error("Unable to start container: %s", container.get("name"))
                            error = True
                    else:
                        logging.error("Unable to clear container: %s", container.get("name"))
                        error = True
                else:
                    logging.error("Unable to stop container: %s", container.get("name"))
                    error = True
            if not error:
                logging.info("Successfully updated all containers!")
                exit(0)
            else:
                logging.error("Docker container upgrade encountered errors, exiting unsuccessfully.")
                exit(1)
        else:
            logging.error("Couldn't find any docker containers. Check DSM UI.")
            exit(1)
    else:
        logging.error("Failed to log into DSM: %s", response.content)
        exit(1)  # Exit with Error



if __name__ == '__main__':
    main(dsm_host, dsm_port, user_name, password, https)
