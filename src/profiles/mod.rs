pub mod agent_replay;

use crate::capsule::Capsule;

pub fn registry() -> Vec<&'static dyn Capsule> {
    vec![&agent_replay::AGENT_ACTION_REPLAY_V1]
}

pub fn find(id: &str) -> Option<&'static dyn Capsule> {
    registry().into_iter().find(|capsule| capsule.id() == id)
}
