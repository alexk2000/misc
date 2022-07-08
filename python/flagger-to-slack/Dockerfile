# ---- Base python ----
FROM python:3.8.1-alpine3.10 AS base
RUN apk add build-base
WORKDIR /app

# ---- Dependencies ----
FROM base AS dependencies  
COPY src/requirements.txt ./
# install app dependencies
RUN pip install -r requirements.txt

# ---- Copy Files/Build ----
FROM dependencies AS build  
COPY src ./
# Build / Compile if required

# --- Release with Alpine ----
FROM python:3.8.1-alpine3.10 AS release  
# Create app directory
WORKDIR /app
COPY --from=dependencies /app/requirements.txt ./
COPY --from=dependencies /root/.cache /root/.cache
# Install app dependencies
RUN pip install -r requirements.txt
COPY --from=build /app/ ./
ENTRYPOINT ["python", "flagger-to-slack.py"]
