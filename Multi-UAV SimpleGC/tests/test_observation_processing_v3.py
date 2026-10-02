"""G3 interface only: E3 integration is deliberately separate."""
import copy
import unittest

from scripts.spike_duplicate_policy import filter_exact_duplicates as spike_filter
from swarm_sim.observation_processing import filter_exact_duplicates, prepare_v3_observations, processing_versions
from swarm_sim.observations import ObservationStream
from swarm_sim.quality import resolve_policy

ORIGIN = dict(lat=30,lon=120,alt_msl_m=0)

def packets():
    result=[]
    for i in range(121):
        for message in (dict(mavpackettype="GLOBAL_POSITION_INT",time_boot_ms=i*100,lat=300000000,lon=1200000000,
                             alt=8000,relative_alt=8000,vx=100,vy=0,vz=0,hdg=0),
                        dict(mavpackettype="SYSTEM_TIME",time_boot_ms=i*100,time_unix_usec=1000000+i*100000)):
            result.append(dict(sysid=1,recv_monotonic_s=100+i/10,message=message))
    return result

class ObservationProcessingV3Tests(unittest.TestCase):
    def prepare(self,rows):
        return prepare_v3_observations(rows,ORIGIN,resolve_policy(),102,110)

    def test_exact_duplicates_in_and_out_of_window_and_v2_frozen(self):
        for offset in (0,100):
            with self.subTest(offset=offset):
                rows=packets()
                rows.insert(offset+1,copy.deepcopy(rows[offset]))
                before=copy.deepcopy(rows)
                result=self.prepare(rows)
                self.assertTrue(result["clock_model"]["available"])
                self.assertTrue(result["samples"])
                self.assertEqual(result["audit"]["dropped_count"],1)
                self.assertEqual(rows,before)
                legacy=ObservationStream(ORIGIN,resolve_policy(),102,110)
                for p in rows:
                    if p["message"]["mavpackettype"]=="GLOBAL_POSITION_INT": legacy.append(p)
                self.assertTrue(legacy.timeline_error)
                self.assertEqual(legacy.samples(),[])

    def test_conflicting_payload_outside_window_invalidates_stream(self):
        rows=packets()
        conflict=copy.deepcopy(rows[0]); conflict["message"]["vx"]=2
        rows.insert(1,conflict)
        result=self.prepare(rows)
        self.assertTrue(result["timeline_error"])
        self.assertEqual(result["samples"],[])
        self.assertFalse(result["audit"]["details"][0]["inside_flight_window"])

    def test_old_exact_payload_is_rollback_not_duplicate(self):
        rows=packets(); rows.insert(4,copy.deepcopy(rows[0]))
        rows[4]["recv_monotonic_s"]=100.1
        result=self.prepare(rows)
        self.assertEqual(result["audit"]["counts"]["GLOBAL_POSITION_INT"]["rollbacks"],1)
        self.assertEqual(result["audit"]["dropped_count"],0)
        self.assertEqual(result["samples"],[])

    def test_system_time_conflict_and_receive_rollback_fail_closed(self):
        for key,value in (("time_unix_usec",42),("host",90)):
            with self.subTest(key=key):
                rows=packets(); duplicate=copy.deepcopy(rows[1])
                if key=="host": duplicate["recv_monotonic_s"]=value
                else: duplicate["message"][key]=value
                rows.insert(2,duplicate)
                result=self.prepare(rows)
                self.assertFalse(result["clock_model"]["available"])
                self.assertEqual(result["samples"],[])

    def test_same_rule_as_accepted_spike_and_version_fields(self):
        rows=packets(); rows.insert(2,copy.deepcopy(rows[1]))
        retained,audit=filter_exact_duplicates(rows)
        old,previous=spike_filter(rows)
        self.assertEqual(retained,old)
        self.assertEqual(audit["counts"],previous["counts"])
        self.assertEqual(audit["details"],previous["details"])
        self.assertEqual(processing_versions()["timeline_policy_version"],"full_stream_strict_v1")
        self.assertEqual(set(processing_versions()),{"observation_processing_version","duplicate_policy_version","timeline_policy_version","clock_model_version"})

    def test_separate_identity_cannot_silently_combine(self):
        rows=packets(); rows[-1]["component_id"]=2
        with self.assertRaisesRegex(ValueError,"one aircraft"):
            self.prepare(rows)

    def test_nonfinite_payload_and_bool_timestamp_remain_invalid(self):
        for key,value in (("time_boot_ms",True),("vx",float("nan"))):
            rows=packets(); rows[0]["message"][key]=value
            self.assertEqual(self.prepare(rows)["samples"],[])

if __name__=="__main__": unittest.main()
