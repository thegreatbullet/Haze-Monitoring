# ADR 0001: One batched message per zone gateway, every 60 seconds

- Status: accepted
- Date: 2026-10-23

## Context
The network has 36 air-quality sensors across 3 zones (North, East, West). AWS IoT Core bills per message (in 5 KB units) plus per rule triggered and per action, and each message also invokes the detector Lambda. Field sensors usually reach the network through a gateway rather than connecting directly. Haze builds up over hours, and NEA's PM2.5 bands are based on 1-hour averages.

## Decision
Each zone has one gateway with its own X.509 certificate. Every 60 seconds it publishes one message to `haze/{zone}/telemetry` containing the readings of all 12 sensors in that zone (about 2 KB).

## Alternatives considered
- One connection and one message per sensor: 12 times more messages, rule runs and Lambda invocations, and 36 certificates to manage instead of 3.
- 10-second readings: 6 times the cost with no benefit, since advisories use 1-hour averages.
- Kinesis Data Streams in front of Lambda: unnecessary at 3 messages a minute, and it adds a fixed hourly cost.

## Consequences
- About 130,000 IoT Core messages a month.
- All three PM2.5 sensors of a zone arrive in one message, so the detector can run the 2-of-3 vote in a single invocation.
- The data lake schema stores readings as an array, queried with UNNEST in Athena.
- A gateway failure takes a whole zone offline, so gateway disconnects must be detected and reported to operators.
