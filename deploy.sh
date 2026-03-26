#!/bin/bash

docker build -t gcr.io/scheduler-demo-491314/scheduler-demo .
docker push gcr.io/scheduler-demo-491314/scheduler-demo

gcloud run deploy scheduler-demo \
--image gcr.io/scheduler-demo-491314/scheduler-demo \
--region us-central1 \
--platform managed \
--allow-unauthenticated
