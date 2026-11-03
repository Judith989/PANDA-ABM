"""CPT parameters and explicitly uncalibrated persona hypotheses.

TK92 monetary-lottery estimates are a benchmark, not parking calibration.
See research/cpt_parameter_provenance.md for sources and transfer limitations.
"""
from dataclasses import asdict,dataclass
import math


@dataclass(frozen=True)
class CPTParameters:
    alpha: float = .88
    beta: float = .88
    lambda_loss: float = 2.25
    gamma: float = .61
    gamma_loss: float = .69

    def __post_init__(self):
        if not (0<self.alpha<=1 and 0<self.beta<=1 and math.isfinite(self.lambda_loss) and self.lambda_loss>0 and .28<=self.gamma<=1 and .28<=self.gamma_loss<=1):
            raise ValueError('Invalid CPT parameters; TK weighting exponents must be in [0.28,1]')

    def as_dict(self):return asdict(self)


SHARED_CPT_PARAMETERS=CPTParameters()
PERSONA_CPT_PROFILES={
    'convenience_seeker':CPTParameters(),
    'cost_sensitive':CPTParameters(),
    'time_sensitive':CPTParameters(),
    'risk_averse':CPTParameters(lambda_loss=3.),
    'accessibility_seeking':CPTParameters(),
}
PERSONA_CPT_PROFILE_VERSION='loss-aversion-hypothesis-v1'


def cpt_parameters_for_persona(persona):
    """Risk-averse lambda=3 is a hypothesis; other profiles retain the benchmark.

    Preference labels alone do not identify five CPT function parameters. No
    ordering is imposed on cost/time/accessibility loss aversion without data.
    """
    try:return PERSONA_CPT_PROFILES[persona]
    except KeyError as exc:raise ValueError(f'Unknown CPT persona: {persona}') from exc
