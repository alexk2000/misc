#!/usr/bin/env python

from aiohttp import web, ClientSession, ClientTimeout
import aiohttp_jinja2
import jinja2
import asyncio
import async_timeout
import aiojobs
from aiojobs.aiohttp import setup, spawn
import time
import sys
import os
import logging
from datetime import datetime
import base64
from cryptography import fernet
import aiohttp_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
import json

logging.basicConfig(level=logging.DEBUG)
routes = web.RouteTableDef()

FLUX_HOST = os.environ.get("FLUX_HOST", "flux-api.kube.devbl")
FLUX_PORT = os.environ.get("FLUX_PORT", "80")
FLUX_POLL_INTERVAL = int(os.environ.get("FLUX_POLL_INTERVAL", 20))

FLUX_API_SERVICES = "/api/flux/v6/services"
FLUX_API_IMAGES = "/api/flux/v6/images"
FLUX_API_RELEASE = "/api/flux/v9/update-manifests"
FLUX_API_JOB_STATUS = "/api/flux/v6/jobs?id="

PORT = 80
SESSION_MAX_AGE = 86400
SHOW_LAST_RELEASE_JOBS = 3
COOKIES_ENC_KEY = b'q1eda4TJHcU3HltPqW9OaiUJ7Qyv-UtxgNtjIR4O0F8='


async def start_background_tasks(app):
    timeout = ClientTimeout(total=5)
    app["client-session"] = ClientSession(timeout=timeout)

async def cleanup_background_tasks(app):
    await app["client-session"].close()

def get_namespaces(services):
    namespaces = set()
    for service in services:
        namespaces.add(service["ID"].split(":")[0])
    return namespaces

def services_by_ns(ns=None, services=None, images=None):
    services_ = []
    for service in services:
        if ns == service["ID"].split(":")[0]:
            for images_ in images:
                if images_["ID"] == service["ID"]:
                    for i, container in enumerate(service["Containers"]):
                        for container_ in images_["Containers"]:
                            if container["Name"] == container_["Name"]:
                                service["Containers"][i]["Images"] = container_
            services_.append(service)
    return services_

async def update(request):
    logging.info("Update started")
    request.app["update_in_progress"] = True
    request.app["update_last_success"] = False
    try:

        services_success = False
        async with request.app["client-session"].get(f"http://{FLUX_HOST}:{FLUX_PORT}{FLUX_API_SERVICES}") as resp:
            if resp.status == 200:
                request.app["services"] = await resp.json()
                logging.info("Update services OK")
                services_success = True
            else:
                logging.info(f"Update services FAILED: response code {resp.status}")
            
        images_success = False
        async with request.app["client-session"].get(f"http://{FLUX_HOST}:{FLUX_PORT}{FLUX_API_IMAGES}") as resp:
            if resp.status == 200:
                request.app["images"] = await resp.json()
                logging.info("Update images OK")
                images_success = True
            else:
                logging.info(f"Update images FAILED: response code {resp.status}")

        if services_success and images_success:
            request.app["update_last_success"] = True
            request.app["update_time"] = int(time.time())
            request.app["ns"] = get_namespaces(request.app["services"])

    except Exception as e:
        logging.info("Update FAILED, exception:" + str(e)) 
        
    request.app["update_in_progress"] = False
    logging.info("Update ended")

async def process_update(request):
    if not request.app["update_in_progress"] and (int(time.time()) - request.app["update_time"]) > FLUX_POLL_INTERVAL:
        await update(request)

async def job_release(request, job_id, wl):
    while True:
        await asyncio.sleep(1)
        async with request.app["client-session"].get(f"http://{FLUX_HOST}:{FLUX_PORT}{FLUX_API_JOB_STATUS}{job_id}") as resp:
            if resp.status == 200:
                job_status = await resp.json()
                job_status["date"] = str(datetime.now())
                job_status["wl"] = wl
                if job_status["StatusString"] == "failed":
                    request.app["jobs_release"][job_id] = job_status
                    logging.info(f"Job {job_id} FAILED:")
                    logging.info(json.dumps(job_status, indent=4))
                    break
                elif job_status["StatusString"] == "succeeded":
                    job_status["Result"].pop("result", None)
                    request.app["jobs_release"][job_id] = job_status
                    logging.info(f"Job {job_id} SUCCESS:")
                    logging.info(json.dumps(job_status, indent=4))
                    break
                          
@routes.get('/status')
async def hello(request):
    return web.Response(text="status")

@routes.get('/metrics')
async def hello(request):
    return web.Response(text="metrics")

@routes.get('/health')
async def hello(request):
    return web.Response(text="health")

@routes.post('/')
async def index(request):
    data = await request.post()
    session = await aiohttp_session.get_session(request)
    if "change-ns" in data:
        session["selected_ns"] = data["selected_ns"]
        return await index(request)
    elif "release" in data:
        post_data = {
            "type": "image",
            "cause": {
                "Message": "",
                "User": ""
            },
            "spec": {
                "ServiceSpecs": [
                    data["wl"]
                ],
                "ImageSpec": f"{data['image']}:{data['tag']}",
                "Kind": "execute",
                "Excludes": None,
                "Force": False
            }
        }
        async with request.app["client-session"].post(f"http://{FLUX_HOST}:{FLUX_PORT}{FLUX_API_RELEASE}", json=post_data) as resp:
            if resp.status == 200:
                job_id = await resp.json()
                message = f"Queued release of {data['wl']} {data['image']}:{data['tag']} job id {job_id}"
                await aiojobs.aiohttp.spawn(request, job_release(request, job_id, data['wl']))              
                logging.info(message)
            else:
                message = f"FAILED release of {data['wl']} {data['image']}:{data['tag']} response code {resp.status}"
                logging.info(message)
                session["error_last"] = message
        if session["jobs_release_ids"] == "":
            session["jobs_release_ids"] = job_id
        else:
            session["jobs_release_ids"] = f'{session["jobs_release_ids"]}:{job_id}'
        raise web.HTTPFound('/')
    else:
        return web.Response(text="Error: unknow POST data")

@routes.get('/')
async def index(request):
    session = await aiohttp_session.get_session(request)
    # if "test" in session: 
        # print(f"Test session {session['test']}")
    if "error_last" not in session:
        session["error_last"] = ""
    if "jobs_release_ids" not in session:
        session["jobs_release_ids"] = ""
    else:
        logging.info(f"Session jobs_release_ids:")
        logging.info(json.dumps(session["jobs_release_ids"], indent=4))
        logging.info(f"All jobs:")
        logging.info(json.dumps(request.app["jobs_release"], indent=4))

    await aiojobs.aiohttp.spawn(request, process_update(request))

    i = 0
    while True:
        if (int(time.time() - request.app["update_time"]) < FLUX_POLL_INTERVAL) and request.app["update_last_success"]:
            break
        await asyncio.sleep(0.1)
        if i > 100:
            return web.Response(text="Fatal: no data (no connection to Flux)")
        i = i + 1

    update_time_str = ""
    if request.app["update_time"]:
        update_time_str = str(datetime.fromtimestamp(request.app["update_time"]))

    jobs_release = []
    if session["jobs_release_ids"]:        
        for job in session["jobs_release_ids"].split(":"):
            if job in request.app["jobs_release"]:
                job_ = request.app["jobs_release"][job]
                job_["job_id"] = job
                jobs_release.append(job_)

    context = {
        "update_time_str": update_time_str,
        "update_time_ts": request.app["update_time"],
        "cur_time_ts": int(time.time()),
        "interval": 3*FLUX_POLL_INTERVAL,
        # "images": request.app["images"],
        # "services": request.app["services"],
        "ns": sorted(request.app["ns"]),
        "error_last": session["error_last"],
        "jobs_release": jobs_release[0-SHOW_LAST_RELEASE_JOBS:]
    }
    request.app["error_last"] = ""
    context["selected_ns"] = session["selected_ns"] if "selected_ns" in session else context["ns"][0]
    # context["selected_ns"] = session["selected_ns"] if "selected_ns" in session else "test-flux"
    context["services"] = services_by_ns(ns=context["selected_ns"], services=request.app["services"], 
        images=request.app["images"])

    return aiohttp_jinja2.render_template("index.html", request, context)

if __name__ == "__main__":
    app = web.Application()
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    app.add_routes(routes)
    app["services"] = []
    app["images"] = []
    app["jobs_release"] = {}
    app["update_in_progress"] = False 
    app["update_last_success"] = False 
    app["update_time"] = 0
    app["ns"] = []
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader("templates"))

    secret_key = base64.urlsafe_b64decode(COOKIES_ENC_KEY)
    aiohttp_session.setup(app, EncryptedCookieStorage(secret_key, max_age=SESSION_MAX_AGE))

    aiojobs.aiohttp.setup(app)
    web.run_app(app, port=PORT, access_log_format='%a %t "%r" %s %b "%{Referer}i" "%{User-Agent}i"')