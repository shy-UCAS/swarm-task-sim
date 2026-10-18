"""Permanent family-only split; no balancing or per-run reassignment."""
import hashlib

SPLIT_RULE = 'u=int(sha256(f"traj2language-v07-fe-split-v1:{family_id}").hexdigest()[:8],16)/2**32; train<0.70; val<0.85; else test'


def family_split(family_id):
    digest = hashlib.sha256(f"traj2language-v07-fe-split-v1:{family_id}".encode()).hexdigest()
    u = int(digest[:8], 16) / 2**32
    return "train" if u < .70 else "val" if u < .85 else "test"
