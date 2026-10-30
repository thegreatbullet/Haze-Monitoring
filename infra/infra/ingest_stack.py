from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_iot as iot
from aws_cdk import aws_sqs as sqs
from cdk_nag import NagSuppressions
from constructs import Construct


class IngestStack(Stack):
    """IoT Core setup for the zone gateways, plus a dead-letter queue for failed messages.

    Each gateway's private key is created on the gateway (here: your laptop) and never
    leaves it. AWS only receives a certificate signing request (CSR) and signs it.
    """

    def __init__(
        self, scope: Construct, construct_id: str, *, gateway_csrs: dict[str, str], **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        for zone, csr in sorted(gateway_csrs.items()):
            name = f"gateway-{zone}"
            label = zone.title()  # "north" -> "North", used in construct IDs and output names
            arn_prefix = f"arn:aws:iot:{self.region}:{self.account}"

            thing = iot.CfnThing(self, f"Thing{label}", thing_name=name)

            cert = iot.CfnCertificate(
                self,
                f"Certificate{label}",
                certificate_signing_request=csr,
                status="ACTIVE",
            )

            # Least privilege: connect only as itself, publish only to its own zone topic.
            policy = iot.CfnPolicy(
                self,
                f"Policy{label}",
                policy_name=f"haze-{name}",
                policy_document={
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": "iot:Connect",
                            "Resource": f"{arn_prefix}:client/{name}",
                            "Condition": {"Bool": {"iot:Connection.Thing.IsAttached": "true"}},
                        },
                        {
                            "Effect": "Allow",
                            "Action": "iot:Publish",
                            "Resource": f"{arn_prefix}:topic/haze/{zone}/telemetry",
                        },
                    ],
                },
            )

            iot.CfnPolicyPrincipalAttachment(
                self, f"PolicyAttachment{label}", policy_name=policy.ref, principal=cert.attr_arn
            )
            iot.CfnThingPrincipalAttachment(
                self, f"ThingAttachment{label}", thing_name=thing.ref, principal=cert.attr_arn
            )

            CfnOutput(self, f"CertificateId{label}", value=cert.ref)

        # Messages the IoT rules or Lambdas fail to process end up here instead of being lost.
        self.dead_letter_queue = sqs.Queue(
            self,
            "IngestDeadLetterQueue",
            queue_name="haze-ingest-dlq",
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl=True,
        )
        NagSuppressions.add_resource_suppressions(
            self.dead_letter_queue,
            [{"id": "AwsSolutions-SQS3", "reason": "This queue is itself the dead-letter queue."}],
        )

        CfnOutput(self, "DeadLetterQueueUrl", value=self.dead_letter_queue.queue_url)
