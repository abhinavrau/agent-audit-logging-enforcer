#!/usr/bin/env python3
"""Utility script to simulate CloudEvent delivery from Eventarc to the local remediation function."""

import argparse
import json
import urllib.request
import uuid


def generate_mock_event(service_type: str, project_id: str, location: str, resource_id: str) -> dict:
    event_id = str(uuid.uuid4())

    if service_type == "dialogflow":
        resource_name = f"projects/{project_id}/locations/{location}/agents/{resource_id}"
        return {
            "specversion": "1.0",
            "type": "google.cloud.audit.log.v1.written",
            "source": f"//dialogflow.googleapis.com/{resource_name}",
            "id": event_id,
            "time": "2026-09-30T18:00:00Z",
            "datacontenttype": "application/json",
            "data": {
                "protoPayload": {
                    "serviceName": "dialogflow.googleapis.com",
                    "methodName": "google.cloud.dialogflow.v3.Agents.CreateAgent",
                    "resourceName": resource_name,
                }
            },
        }
    elif service_type == "discoveryengine":
        resource_name = f"projects/{project_id}/locations/{location}/collections/default_collection/engines/{resource_id}"
        return {
            "specversion": "1.0",
            "type": "google.cloud.audit.log.v1.written",
            "source": f"//discoveryengine.googleapis.com/{resource_name}",
            "id": event_id,
            "time": "2026-09-30T18:00:00Z",
            "datacontenttype": "application/json",
            "data": {
                "protoPayload": {
                    "serviceName": "discoveryengine.googleapis.com",
                    "methodName": "google.cloud.discoveryengine.v1.EngineService.CreateEngine",
                    "resourceName": resource_name,
                }
            },
        }
    else:
        raise ValueError(f"Unknown service type: {service_type}")


def main():
    parser = argparse.ArgumentParser(description="Send mock Eventarc CloudEvent to remediator.")
    parser.add_argument("--url", default="http://127.0.0.1:8080", help="Function endpoint URL")
    parser.add_argument("--type", choices=["dialogflow", "discoveryengine"], default="dialogflow")
    parser.add_argument("--project", default="sample-test-project")
    parser.add_argument("--location", default="us-central1")
    parser.add_argument("--resource-id", default="my-new-agent")
    args = parser.parse_args()

    event = generate_mock_event(args.type, args.project, args.location, args.resource_id)
    payload_bytes = json.dumps(event).encode("utf-8")

    req = urllib.request.Request(
        args.url,
        data=payload_bytes,
        headers={
            "Content-Type": "application/cloudevents+json",
            "ce-id": event["id"],
            "ce-specversion": event["specversion"],
            "ce-type": event["type"],
            "ce-source": event["source"],
        },
        method="POST",
    )

    print(f"Sending mock CloudEvent ({args.type}) to {args.url}...")
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Response status: {resp.status}")
            print(f"Response body: {resp.read().decode('utf-8')}")
    except Exception as e:
        print(f"Request failed: {e}")


if __name__ == "__main__":
    main()
