import math
import random

from modules.utils import config


def _normalise_model_name(model_name):
    return str(model_name or "Perfect").replace("-", "").replace("_", "").lower()


class CommunicationModel:
    """Base interface for packet-level communication decisions."""

    def should_receive(self, sender, receiver, message, simulation_time=None):
        raise NotImplementedError


class PerfectCommunicationModel(CommunicationModel):
    def should_receive(self, sender, receiver, message, simulation_time=None):
        return True


class BernoulliCommunicationModel(CommunicationModel):
    def __init__(self, p_success, rng):
        self.p_success = max(0.0, min(1.0, float(p_success)))
        self.rng = rng

    def should_receive(self, sender, receiver, message, simulation_time=None):
        return self.rng.random() <= self.p_success


class GilbertElliotCommunicationModel(CommunicationModel):
    GOOD = "Good"
    BAD = "Bad"

    def __init__(
        self,
        p_good_success,
        p_bad_success,
        p_good_to_good,
        p_bad_to_bad,
        transition_interval_seconds,
        initial_state,
        rng,
    ):
        self.p_good_success = max(0.0, min(1.0, float(p_good_success)))
        self.p_bad_success = max(0.0, min(1.0, float(p_bad_success)))
        self.p_good_to_good = max(0.0, min(1.0, float(p_good_to_good)))
        self.p_bad_to_bad = max(0.0, min(1.0, float(p_bad_to_bad)))
        self.transition_interval_seconds = max(float(transition_interval_seconds), 0.0)
        self.initial_state = self.GOOD if str(initial_state).lower() == "good" else self.BAD
        self.rng = rng
        self.link_states = {}
        self.last_transition_times = {}

    def should_receive(self, sender, receiver, message, simulation_time=None):
        link_id = (sender.agent_id, receiver.agent_id)
        state = self._state_for_link(link_id, simulation_time)
        p_success = self.p_good_success if state == self.GOOD else self.p_bad_success
        return self.rng.random() <= p_success

    def _state_for_link(self, link_id, simulation_time):
        if link_id not in self.link_states:
            self.link_states[link_id] = self.initial_state
            self.last_transition_times[link_id] = 0.0 if simulation_time is None else simulation_time

        self._advance_link_state(link_id, simulation_time)
        return self.link_states[link_id]

    def _advance_link_state(self, link_id, simulation_time):
        if self.transition_interval_seconds <= 0:
            self._transition_once(link_id)
            return

        if simulation_time is None:
            self._transition_once(link_id)
            return

        last_time = self.last_transition_times[link_id]
        while simulation_time - last_time >= self.transition_interval_seconds:
            self._transition_once(link_id)
            last_time += self.transition_interval_seconds
        self.last_transition_times[link_id] = last_time

    def _transition_once(self, link_id):
        state = self.link_states[link_id]
        if state == self.GOOD:
            self.link_states[link_id] = self.GOOD if self.rng.random() <= self.p_good_to_good else self.BAD
        else:
            self.link_states[link_id] = self.BAD if self.rng.random() <= self.p_bad_to_bad else self.GOOD


class RayleighFadingCommunicationModel(CommunicationModel):
    def __init__(
        self,
        transmit_power_db,
        sensitivity_threshold_db,
        path_loss_at_reference_db,
        reference_distance,
        path_loss_exponent,
        fading_scale,
        rng,
    ):
        self.transmit_power_db = float(transmit_power_db)
        self.sensitivity_threshold_db = float(sensitivity_threshold_db)
        self.path_loss_at_reference_db = float(path_loss_at_reference_db)
        self.reference_distance = max(float(reference_distance), 1e-9)
        self.path_loss_exponent = float(path_loss_exponent)
        self.fading_scale = max(float(fading_scale), 1e-9)
        self.rng = rng

    def should_receive(self, sender, receiver, message, simulation_time=None):
        distance = max(sender.position.distance_to(receiver.position), self.reference_distance)
        path_loss_db = self.path_loss_at_reference_db + (
            10.0 * self.path_loss_exponent * math.log10(distance / self.reference_distance)
        )

        # Rayleigh fading is sampled as a channel envelope and converted to dB.
        # Low envelope values become extra attenuation; high values can briefly help reception.
        fading_envelope = self._sample_rayleigh(self.fading_scale)
        fading_gain_db = 20.0 * math.log10(max(fading_envelope, 1e-12))
        received_power_db = self.transmit_power_db - path_loss_db + fading_gain_db
        return received_power_db >= self.sensitivity_threshold_db

    def _sample_rayleigh(self, scale):
        u = max(self.rng.random(), 1e-12)
        return scale * math.sqrt(-2.0 * math.log(u))


def build_communication_model():
    communication_config = config.get("communication", {}) if config else {}
    rng = random.Random(communication_config.get("random_seed"))
    model_name = _normalise_model_name(communication_config.get("model", "Perfect"))

    if model_name == "perfect":
        return PerfectCommunicationModel()

    if model_name == "bernoulli":
        params = communication_config.get("bernoulli", {})
        return BernoulliCommunicationModel(params.get("p_success", 1.0), rng)

    if model_name in {"gilbertelliot", "ge"}:
        params = communication_config.get("gilbert_elliot", {})
        return GilbertElliotCommunicationModel(
            p_good_success=params.get("p_good_success", 1.0),
            p_bad_success=params.get("p_bad_success", 0.0),
            p_good_to_good=params.get("p_good_to_good", 0.9),
            p_bad_to_bad=params.get("p_bad_to_bad", 0.9),
            transition_interval_seconds=params.get("transition_interval_seconds", 1.0),
            initial_state=params.get("initial_state", "Good"),
            rng=rng,
        )

    if model_name == "rayleigh":
        params = communication_config.get("rayleigh", {})
        return RayleighFadingCommunicationModel(
            transmit_power_db=params.get("transmit_power_db", 30.0),
            sensitivity_threshold_db=params.get("sensitivity_threshold_db", -65.0),
            path_loss_at_reference_db=params.get("path_loss_at_reference_db", 40.0),
            reference_distance=params.get("reference_distance", 1.0),
            path_loss_exponent=params.get("path_loss_exponent", 2.5),
            fading_scale=params.get("fading_scale", 1.0),
            rng=rng,
        )

    raise ValueError(f"[ERROR] Unknown communication model: {communication_config.get('model')}")
