#!/usr/bin/env bash
# After `cdk deploy HazeIngest`: downloads each gateway's signed certificate and
# Amazon's root CA into certs/, then prints the IoT endpoint for the simulator.
set -euo pipefail
cd "$(dirname "$0")/.."

for zone in north east west; do
  label="$(echo "${zone:0:1}" | tr '[:lower:]' '[:upper:]')${zone:1}"   # north -> North
  cert_id=$(aws cloudformation describe-stacks --stack-name HazeIngest \
    --query "Stacks[0].Outputs[?OutputKey=='CertificateId$label'].OutputValue" --output text)
  aws iot describe-certificate --certificate-id "$cert_id" \
    --query certificateDescription.certificatePem --output text > "certs/gateway-$zone/certificate.pem.crt"
  echo "Saved certificate for gateway-$zone"
done

curl -sS -o certs/AmazonRootCA1.pem https://www.amazontrust.com/repository/AmazonRootCA1.pem
echo "Saved Amazon root CA"

echo
echo "IoT endpoint:"
aws iot describe-endpoint --endpoint-type iot:Data-ATS --query endpointAddress --output text
