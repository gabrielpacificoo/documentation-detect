from .microservices import MicroservicesDetector
from .procedures import ProceduresDetector
from .tables import TablesDetector


def default_detectors():
    return [ProceduresDetector(), MicroservicesDetector(), TablesDetector()]
