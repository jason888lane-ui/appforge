"""Provider-neutral, plan-only cloud adapters.

No SDKs, credentials, account discovery, or apply operations are invoked here.
The returned plans are proposals for a future approval-gated execution service.
"""
from dataclasses import dataclass
from enum import StrEnum


class CloudProvider(StrEnum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


@dataclass(frozen=True)
class DeploymentPlan:
    provider: CloudProvider
    environment: str
    region: str
    proposed_services: tuple[str, ...]
    actions: tuple[str, ...]
    apply_enabled: bool = False


class CloudAdapter:
    provider: CloudProvider
    services: tuple[str, ...]

    def plan(self, *, environment: str, region: str) -> DeploymentPlan:
        if environment not in {"development", "staging", "production"}:
            raise ValueError("Unsupported environment.")
        if not region.strip():
            raise ValueError("A region is required.")
        return DeploymentPlan(
            provider=self.provider,
            environment=environment,
            region=region,
            proposed_services=self.services,
            actions=(
                "Validate account and regional service availability",
                "Generate infrastructure-as-code preview",
                "Estimate cost and security posture",
                "Request human approval before any apply operation",
            ),
        )


class AWSAdapter(CloudAdapter):
    provider = CloudProvider.AWS
    services = ("container runtime", "managed PostgreSQL", "object storage", "secret manager")


class AzureAdapter(CloudAdapter):
    provider = CloudProvider.AZURE
    services = ("container apps", "managed PostgreSQL", "blob storage", "key vault")


class GCPAdapter(CloudAdapter):
    provider = CloudProvider.GCP
    services = ("Cloud Run", "Cloud SQL", "Cloud Storage", "Secret Manager")


ADAPTERS: dict[CloudProvider, CloudAdapter] = {
    CloudProvider.AWS: AWSAdapter(),
    CloudProvider.AZURE: AzureAdapter(),
    CloudProvider.GCP: GCPAdapter(),
}


def create_deployment_plan(
    *, provider: CloudProvider, environment: str, region: str
) -> DeploymentPlan:
    return ADAPTERS[provider].plan(environment=environment, region=region)
