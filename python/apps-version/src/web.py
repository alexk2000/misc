from aiohttp import web, ClientSession, ClientTimeout
from prometheus_async import aio
from prometheus_client import Gauge
import asyncio
import aiojobs
import random
import logging
import os
import pprint 
import yaml
import sys

CONFIG_FILE = 'conf/config.yml'

routes = web.RouteTableDef()
# Prometheus metrics
app_version = Gauge('app_version', 'Application version', ['app', 'version', 'env'])

# needed to avoid metric duplication (old version for the same app)
app_version_cur = {}

@routes.get('/health')
async def hello(request):
    return web.Response(text='healthy')

async def scrape_job(app, svc):
    version_ = app_version_cur.pop((svc['name'], config['env']), None)
    if version_:
        app_version.remove(svc['name'], version_, config['env'])

    try:
        async with app["client-session"].get(svc['url']) as resp:
            version = {
                    'app': svc['name'],
                    'version': 'NONE',
                    'env':  config['env'],
                    svc['name']: '1'
            }
            if resp.status == 200:
                resp_text = await resp.text()
                resp_list = resp_text.split()
                if len(resp_list) == 1:
                    version_ = resp_text
                elif len(resp_list) == 2:
                    version_ = resp_list[1]
                app_version.labels(app=svc['name'], version=version_, env=config['env']).set(1)
                app_version_cur[(svc['name'], config['env'])] = version_
                logging.debug(f"{svc['name']}, {version_}, {config['env']}")
            else:
                logging.error(f"{svc['name']}, {config['env']}, response code {resp.status}")
                app_version.labels(app=svc['name'], version='NONE', env=config['env']).set(0)
                app_version_cur[(svc['name'], config['env'])] = 'NONE'
    except Exception as e:
        logging.error(f"{svc['name']}, {config['env']}, exception raised {type(e)}")
        app_version.labels(app=svc['name'], version='NONE', env=config['env']).set(0)
        app_version_cur[(svc['name'], config['env'])] = 'NONE'

async def schedule_job(app, svc):
    scheduler = await aiojobs.create_scheduler()
    while True:
        await scheduler.spawn(scrape_job(app=app, svc=svc))
        await asyncio.sleep(config['interval'])

async def scrape(app):
    await asyncio.gather(*[schedule_job(app=app,svc=svc) for svc in config['services']])

async def start_background_tasks(app):
    timeout = ClientTimeout(total=config['timeout'])
    app["client-session"] = ClientSession(timeout=timeout)
    app['scrape'] = asyncio.create_task(scrape(app))

async def cleanup_background_tasks(app):
    app['scrape'].cancel()
    await app['scrape']
    await app["client-session"].close()

if __name__ == '__main__':
    try:
        with open(CONFIG_FILE, 'r') as ymlfile:
            config = yaml.load(ymlfile)
    except Exception as e:
        logging.fatal(f"can't open configuration file {CONFIG_FILE},  {e}\n")
        sys.exit(1)

    logging.basicConfig(level=config['level'])
    app = web.Application()
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    app.add_routes(routes)
    app.router.add_get('/metrics', aio.web.server_stats)
    web.run_app(app, port=config['port'], access_log_format='%a %t "%r" %s %b "%{Referer}i" "%{User-Agent}i" ')
