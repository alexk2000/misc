#!/usr/bin/env python

from aiohttp import web, ClientSession
import logging
import sys
import os

VERSION = ""
logging.basicConfig(level=logging.DEBUG)
routes = web.RouteTableDef()
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
if not WEBHOOK_URL:
    logging.fatal("Env variable WEBHOOK_URL not set")
    sys.exit(1)

@routes.get('/health')
async def health(request):
    return web.Response(text="OK")

@routes.post('/flagger2slack')
async def flagger2slack(request):
    data = await request.json()
    if data['metadata']['eventType'] == "Warning":
        color = "warning"
        if data['phase'] == "Failed":
            color = "danger"
    else:
        color = "normal"
        if data['phase'] == "Finalising":
            color = "good"

    message = {
        "username": "flagger",
        "icon_emoji": ":rocket:",
        "attachments": [
            {
                "title": "Flagger notification",
                "text": data['phase'],
                "color": color,
                "fields": [
                    {
                        "title": "Name",
                        "value": data['name'],
                        "short": "true"
                    },
                    {
                        "title": "Namespace",
                        "value": data['namespace'],
                        "short": "true"
                    },
                    {
                        "title": "Phase",
                        "value": data['phase'],
                        "short": "false"
                    },
                    {
                        "title": "Event message",
                        "value": data['metadata']['eventMessage'],
                        "short": "false"
                    },
                    {
                        "title": "Event type",
                        "value": data['metadata']['eventType'],
                        "short": "false"
                    }
                ],
                "ts": data['metadata']['timestamp']
            }
        ]
    }

    async with ClientSession() as session:
        async with session.post(WEBHOOK_URL, json=message) as resp:
            print(resp.status)
            print(await resp.text())
    return web.json_response({"status": "OK"})

app = web.Application()
app.add_routes(routes)
web.run_app(app, port=80)