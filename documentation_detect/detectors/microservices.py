import ipaddress
from urllib.parse import urlsplit

from ..models import AnalysisContext, Findings


def service_host(url: str | None) -> str | None:
    if not url or "${" in url:
        return None
    try:
        hostname = urlsplit(url if "://" in url else "//" + url).hostname
    except ValueError:
        return None
    if not hostname or hostname in {"localhost", "host.docker.internal"}:
        return None
    try:
        ipaddress.ip_address(hostname)
        return None
    except ValueError:
        return hostname


class MicroservicesDetector:
    def detect(self, context: AnalysisContext, findings: Findings) -> None:
        for source in context.java:
            config = context.configurations[source.source.main_root]
            for annotation in source.annotations:
                if annotation.name != "FeignClient":
                    continue
                declared = source.value(annotation, "name") or source.value(annotation)
                name = config.resolve(declared)
                url = config.resolve(source.value(annotation, "url"))
                configured_name = name if declared and "${" in declared else None
                service = configured_name or service_host(url) or name or source.class_after(annotation.end)
                if service:
                    findings.microsservicos.add(service)
