"""V8-20 本地几何/冻结接口预置测试。未经运行。"""
import copy
import math
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import shapely
from task_v07 import detectors
from v08.contract.monitoring import TaskSpec,MemberPlan,SegmentPlan
from v08.contract.single_intent import AreaSearchTaskSpec
from v08.motion.area_search_geometry import minimum_inner_offset
from v08.motion.area_search_checks import screen_area_search
from v08.motion.skeleton import references_from_skeleton
from v08.motion.optimize import turns_from_skeleton
from v08.runner.area_search_serialization import task_record,validate_survey


def fixture(center=(0.,0.)):
    g = {"type":"Circle","center_m":list(center),"radius_m":1.}
    offsets = {"warning":200.,"alert":50.,"protected":25.}
    layers = {k:{"type":"Circle","center_m":list(center),"radius_m":1.+v}
              for k,v in offsets.items()}
    fac = NS(id="f",geometry=g,center=np.array(center),offsets=offsets,layers=layers)
    world = {"type":"Polygon","vertices_m":[[-1000.,-1000.],[1000.,-1000.],
                                                   [1000.,1000.],[-1000.,1000.]]}
    entities = [{"id":"f","type":"facility","geometry":g}]
    entities += [{"id":"f_"+k,"type":"zone","facility_id":"f","layer":k,
                  "offset_m":v,"geometry":layers[k]} for k,v in offsets.items()]
    return {"world":{"geometry":world},"entities":entities}, [fac]


def survey_fixture():
    # 合法序列化夹具；每个字段均有确定来源，绝非空占位字典。
    s = {"type":"ContourAnnularSector",
         "base_geometry":{"type":"Circle","center_m":[0.,0.],"radius_m":100.},
         "center_m":[0.,0.],"inner_offset_m":200.,"outer_offset_m":400.,
         "start_angle_rad":-math.pi/12,"angle_span_rad":math.pi/6,
         "bounding_radius_m":500.}
    area = (500.**2-300.**2)*(math.pi/6)/2
    return {"geometry":s,"bounds_m":[-500.,-500.,500.,500.],"footprint_radius_m":50.,
            "grid_spacing_m":min(25.,math.sqrt(area)/50),"strip_count":4,
            "strips_per_member":2,"area_m2":area}


class LocalGeometryPreset(unittest.TestCase):
    def test_minimal_inner_circle(self):
        # 圆弦等式的解析根；不从新circle helper获得oracle。
        angles = np.radians([-11.25,-3.75,3.75,11.25])
        got = minimum_inner_offset({"type":"Circle","center_m":[0.,0.],"radius_m":100.},
                                   (0.,0.),angles,400.,150.)
        want = 150. + .5*math.ceil((40./(2.*math.sin(math.radians(3.75)))-100.-150.)/.5)
        self.assertAlmostEqual(got,want,delta=1e-9)

    def test_two_point_five_footprints_cover_only_three_fifths(self):
        scene, facilities = fixture((-100.,0.))
        # 12.5×10矩形，步0.5：25×20=500点；每条带只盖3列，5条盖15列。
        survey = {"geometry":{"type":"Polygon","vertices_m":[[0.,0.],[12.5,0.],
                                                                       [12.5,10.],[0.,10.]]},
                  "bounds_m":[0.,0.,12.5,10.],"footprint_radius_m":1.,"grid_spacing_m":.5}
        samples = {}
        for j,x in enumerate((1.25,3.75,6.25,8.75,11.25)):
            p = np.c_[np.full(10,x),np.arange(.5,10.,1.),np.full(10,100.)]
            samples[str(j)] = {"time_us":np.arange(10,dtype=np.int64)*100000,
                               "p":p,"v":np.tile([0.,10.,0.],(10,1))}
        # 冻结函数wrap证明适配确实调用它；不替换其返回值。
        with patch.object(detectors,"coverage",wraps=detectors.coverage) as frozen:
            out = screen_area_search(scene,facilities,"f",samples,survey)
        self.assertEqual(frozen.call_count,5)
        # 点到最近采样纵向差0.25，横向差1时距离²=1.0625>1，所以非5/5覆盖。
        self.assertEqual(out["group_facts"]["grid_point_count"],500)
        self.assertEqual(out["group_facts"]["covered_grid_point_count"],300)
        self.assertEqual(out["group_facts"]["coverage_fraction"],.6)
        self.assertFalse(out["group_conditions"]["shared_coverage"])
        self.assertFalse(out["passed"])

    def test_120_degree_counterexample_rejected(self):
        scene, facilities = fixture()
        a = np.radians(np.arange(-60.,61.,1.))
        arc = 100.*np.c_[np.cos(a),np.sin(a)]
        xy = np.vstack([2.2*arc[0],arc,2.2*arc[-1]])
        p = np.c_[xy,np.full(len(xy),100.)]
        samples = {"m":{"time_us":np.arange(len(xy),dtype=np.int64)*100000,
                         "p":p,"v":np.tile([4.,0.,0.],(len(xy),1))}}
        survey = {"geometry":{"type":"Circle","center_m":[0.,0.],"radius_m":150.},
                  "bounds_m":[-150.,-150.,150.,150.],"footprint_radius_m":50.,"grid_spacing_m":25.}
        out = screen_area_search(scene,facilities,"f",samples,survey)
        # 最大圆周间隙240°，完整warning访问覆盖120°，超过U预筛110°。
        self.assertAlmostEqual(out["member_facts"]["m"]["azimuth_span_deg"],120.,delta=1e-9)
        self.assertFalse(out["member_conditions"]["m"]["azimuth_span_ok"])
        self.assertFalse(out["passed"])

    def test_survey_only_on_area_search_and_strict_nested_shape(self):
        expected = {"task_id":"t","intent":"transit","target_id":"f",
                    "switch_mode":"auto","final":True}
        # S TaskSpec五键，旧五意图不增加空survey。
        self.assertEqual(task_record(TaskSpec("t","transit","f")),expected)
        for intent in ("monitoring","transit","intrusion","feint","close_observation"):
            self.assertNotIn("survey",task_record(TaskSpec("t",intent,"f")))
        s = survey_fixture()
        t = AreaSearchTaskSpec("t","area_search","f",survey=s)
        self.assertEqual(task_record(t)["survey"],s)
        # 白名单独立负例：top、sector、base_geometry三个层级的运行字段都非法。
        for level,key,value in ((0,"wall_s",1.),(1,"cache_hits",1),
                                (2,"path","C:/private/run"),(0,"unknown",{})):
            bad = copy.deepcopy(s)
            target = bad if level==0 else bad["geometry"] if level==1 else bad["geometry"]["base_geometry"]
            target[key] = value
            with self.assertRaises(ValueError):
                validate_survey(bad)

    def test_independent_member_references_and_turn_time(self):
        # 两条独立完整直线，长度40/60，方向正交，节点0.5m；没有隐含场景依赖。
        xy_a = tuple((float(x),0.) for x in np.arange(0.,40.5,.5))
        xy_b = tuple((10.,float(y)) for y in np.arange(0.,60.5,.5))
        mps = {"a":MemberPlan("a",0,xy_a,100.,40.,0.,((0.,4.),)),
               "b":MemberPlan("b",0,xy_b,100.,60.,.3,((0.,4.),))}
        independent = {}
        for mid,xy,L in (("a",xy_a,40.),("b",xy_b,60.)):
            independent[mid] = {"vertices_xy":[xy[0],xy[-1]],"radii_m":[],"primitives":[],
                "curve_s":np.arange(0.,L+.5,.5).tolist(),"collect_s":5.,"split_s":10.,
                "scan_start_s":10.,"scan_end_s":L-10.,"warning_entry_s":7.,
                "warning_exit_s":L-5.,"terminal_s":L,"block_index":0 if mid=="a" else 1,
                "strip_indices":[0,1] if mid=="a" else [2,3],"first_outer_omitted":False,
                "slot_xy":xy[20],"head_kind":"fixture"}
        plan = SegmentPlan(members=mps,reference_xy=(),nominal_duration_s=0.,anchors={},repairs=(),
                           proposal={},formation={},topology={"final":"area_search"},business_key={},
                           member_nominal_s={},witnesses={"intent":"area_search","target_id":"f",
                           "survey":survey_fixture(),"independent_members":independent,"turn_ranges":{}})
        refs,lines,maps = references_from_skeleton(plan)
        self.assertEqual(len(refs),2)  # 一成员一独立参考；不需要公共reference_xy。
        self.assertEqual(lines,())     # warnings=None，没有伪造穿越直线。
        for ref in refs:
            nom = maps[ref.member_id]["nominal"]
            p0 = np.asarray(mps[ref.member_id].curve_xy[0])
            p1 = np.asarray(mps[ref.member_id].curve_xy[-1])
            # 起点精确；绝对时刻加再减release可能相差1ulp，末点仅比较表示误差界。
            # 1e-9来自V8-19浮点裁定，不要求冻结NominalPVA更改绝对时间求值。
            f = maps[ref.member_id]["nominal"]
            from v08.motion.skeleton import NominalPVA
            np.testing.assert_array_equal(NominalPVA(f)(ref.release_s)[0],p0)
            np.testing.assert_allclose(NominalPVA(f)(ref.release_s+nom.travel_s)[0],p1,rtol=0.,atol=1e-9)
            self.assertEqual(ref.end_s,ref.release_s+nom.travel_s)
            self.assertEqual(ref.release_s+(ref.end_s-ref.release_s),ref.end_s)
        # 手工到达表：s=5、20插值到局部t=1、4；加release20得到21、24。
        nom = NS(curve=NS(s=np.array([0.,10.,30.])),t_nodes=np.array([0.,2.,6.]),release_s=20.)
        sk = NS(witnesses={"turn_ranges":{"m":[("u",5.,20.,"turn_u_min_m")]}})
        got = turns_from_skeleton(sk,{"m":{"nominal":nom}},{"turn_u_min_m":15.})
        self.assertEqual(got,(("m",21.,24.,15.),))


if __name__ == "__main__":
    unittest.main()
