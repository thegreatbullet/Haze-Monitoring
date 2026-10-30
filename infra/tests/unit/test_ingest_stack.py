import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from infra.ingest_stack import IngestStack

ACCOUNT = "123456789012"
REGION = "ap-southeast-1"
FAKE_CSR = "-----BEGIN CERTIFICATE REQUEST-----\nFAKE\n-----END CERTIFICATE REQUEST-----\n"


def _template() -> Template:
    app = cdk.App()
    stack = IngestStack(
        app,
        "TestIngest",
        gateway_csrs={"north": FAKE_CSR, "east": FAKE_CSR, "west": FAKE_CSR},
        env=cdk.Environment(account=ACCOUNT, region=REGION),
    )
    return Template.from_stack(stack)


def test_one_thing_and_active_certificate_per_zone():
    template = _template()
    template.resource_count_is("AWS::IoT::Thing", 3)
    template.resource_count_is("AWS::IoT::Certificate", 3)
    for zone in ("north", "east", "west"):
        template.has_resource_properties("AWS::IoT::Thing", {"ThingName": f"gateway-{zone}"})
    template.has_resource_properties(
        "AWS::IoT::Certificate", {"CertificateSigningRequest": FAKE_CSR, "Status": "ACTIVE"}
    )


def test_gateway_west_can_only_publish_to_its_own_zone():
    _template().has_resource_properties(
        "AWS::IoT::Policy",
        {
            "PolicyName": "haze-gateway-west",
            "PolicyDocument": {
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "iot:Connect",
                        "Resource": f"arn:aws:iot:{REGION}:{ACCOUNT}:client/gateway-west",
                        "Condition": {"Bool": {"iot:Connection.Thing.IsAttached": "true"}},
                    },
                    {
                        "Effect": "Allow",
                        "Action": "iot:Publish",
                        "Resource": f"arn:aws:iot:{REGION}:{ACCOUNT}:topic/haze/west/telemetry",
                    },
                ],
            },
        },
    )


def test_each_certificate_is_attached_to_its_thing_and_policy():
    template = _template()
    template.resource_count_is("AWS::IoT::ThingPrincipalAttachment", 3)
    template.resource_count_is("AWS::IoT::PolicyPrincipalAttachment", 3)


def test_dead_letter_queue_is_encrypted_and_keeps_messages_14_days():
    _template().has_resource_properties(
        "AWS::SQS::Queue",
        {"QueueName": "haze-ingest-dlq", "SqsManagedSseEnabled": True, "MessageRetentionPeriod": 1209600},
    )


def test_dead_letter_queue_rejects_unencrypted_connections():
    _template().has_resource_properties(
        "AWS::SQS::QueuePolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {"Effect": "Deny", "Condition": {"Bool": {"aws:SecureTransport": "false"}}}
                        )
                    ]
                )
            }
        },
    )
