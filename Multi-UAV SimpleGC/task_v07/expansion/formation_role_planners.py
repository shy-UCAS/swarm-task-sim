"""Role geometries built from phase-1 formation corridors and exact contour roots."""
import math,random
from collections import defaultdict
import numpy as np
from scene_v07.geometry import center_of
from task_v07.geometry import geometry_facts,offset_geometry
from task_v07.planning import seed_for,clean_route
from task_v07.visibility import ExactVisibilityPlanner
from .contracts import RouteBundle
from .formation_corridors import offset_polyline,start_line,shared_reference_corridor
from .geometry_checks import check_retreat_point,check_polyline
from .candidate_constraints import bearing_allowed

VERSION='v07_s2x_formation_roles_v1'


def contour_point(geometry,center,outward,offset,lateral):
    normal=np.array([-outward[1],outward[0]])
    origin=center+lateral*normal
    if float(geometry_facts(geometry,origin)['signed_distance_m'])>offset:
        return None
    lo,hi=0.,max(1.,offset+100.)
    while float(geometry_facts(geometry,origin+hi*outward)['signed_distance_m'])<offset:hi*=2
    for _ in range(55):
        mid=(lo+hi)/2
        if float(geometry_facts(geometry,origin+mid*outward)['signed_distance_m'])<offset:lo=mid
        else:hi=mid
    return origin+hi*outward


def stable_split(family,members,slot,multi):
    # Digital slot and physical ID set only: no column, role or timing seed.
    order=sorted(s['agent_id'] for s in family['initial_states'])
    random.Random(seed_for(family.get('sampling_seed',0),f'geometry-split-slot:{slot}')).shuffle(order)
    sequence=[a for a in order if a in set(members)]
    if not multi:return [sequence]
    cut=(len(sequence)+1)//2
    return [sequence[:cut],sequence[cut:]]


class Context:
    def __init__(self,scene,group,params):
        from .role_planners import zones_of
        self.scene,self.group,self.params=scene,group,params
        self.family=params['family'];self.role=group['role']
        self.retreat_warning_minimum_m=float(params.get('retreat_warning_minimum_m',200.))
        self.facility,self.zones=zones_of(scene,group['target_id'])
        self.geometry=self.facility['geometry'];self.center=np.asarray(center_of(self.geometry))
        self.states={s['agent_id']:s for s in self.family['initial_states']}
        self.starts={a:np.asarray(self.states[a]['position_enu_m'][:2],float) for a in group['members']}
        self.multi=params['approach_mode']=='multi_direction'
        self.slot=params.get('geometry_slot',0)
        self.split=stable_split(self.family,group['members'],self.slot,self.multi)
        if params.get('common_slot') is not None:
            from .public_approach_shape import public_approach_shape
            self.public_shape=public_approach_shape(self.family,params['common_slot'],group['members'],self.multi)
            self.split=self.public_shape['members']
            self.relative_bearings_rad=self.public_shape['relative_bearings_rad']
        self.rng=random.Random(params.get('geometry_seed',params['planning_seed']))
        self.speed=self.family['cruise_speed_m_s'];self.altitude=self.family['task_altitude_m']
        self._planners={}
        # Explicit heterogeneous margins: hard restrictions 35m; semantic layers
        # require no entry, with 5m M3 tracking pad (feint protected pad 35m).
        self.forbidden=[]
        for entity in scene['entities']:
            if entity.get('layer')=='alert' and (entity['facility_id']!=group['target_id'] or self.role not in ('feint','intrusion')):
                self.forbidden.append((entity,5.))
            if entity.get('layer')=='protected' and entity['facility_id']==group['target_id'] and self.role=='feint':
                self.forbidden.append((entity,35.))

    def planner(self,margin=35.,warnings=False):
        key=(math.ceil(margin),warnings)
        if key not in self._planners:
            from copy import deepcopy
            copy=deepcopy(self.scene)
            for entity in copy['entities']:
                forbidden=next((pad for e,pad in self.forbidden if e['id']==entity['id']),None)
                if entity['type']=='hard_constraint_obstacle':
                    entity['geometry']=offset_geometry(entity['geometry'],float(math.ceil(margin)))
                elif warnings and entity.get('layer')=='warning' and (not self.params.get('target_warning_only') or entity['facility_id']==self.group['target_id']):
                    entity['type']='hard_constraint_obstacle'
                    entity['geometry']=offset_geometry(entity['geometry'],float(math.ceil(margin)))
                elif forbidden is not None:
                    entity['type']='hard_constraint_obstacle'
                    entity['geometry']=offset_geometry(entity['geometry'],forbidden)
            # Each private obstacle already has its explicit exact contour pad.
            self._planners[key]=ExactVisibilityPlanner(copy,0.)
        return self._planners[key]

    def route_valid(self,points):
        if not check_polyline(self.scene,[[*p,self.altitude] for p in points],margin_m=35.)['valid']:return False
        for e,pad in self.forbidden:
            for a,b in zip(points,points[1:]):
                if geometry_facts(e['geometry'],np.asarray([a,b]),footprint=True)['clearance_m']<pad-1e-6:return False
        return True

    def retreat(self,point,outward):
        distances=([self.rng.uniform(100.,3500.) for _ in range(12)] if getattr(self,'continuous_candidate',False)
                   else np.arange(100.,3500.,25.))
        for distance in distances:
            q=np.asarray(point)+distance*outward
            if (check_retreat_point(self.scene,q,warning_clearance_m=self.retreat_warning_minimum_m)['valid'] and
                (self.planner().visible(point.tolist(),q.tolist()) if self.role=='feint' else
                 self.planner().path(point.tolist(),q.tolist()) is not None)):
                return q
        return None

    def lead(self,origin,outward,margin,half):
        for distance in np.arange(200.,3500.,25.):
            p=origin+distance*outward
            if (self.planner(margin,warnings=True).free(p.tolist())
                and all(float(geometry_facts(e['geometry'],p)['signed_distance_m'])>0
                        for e in self.scene['entities'] if e.get('layer')=='warning')):
                return p
        return None


def core_path_length(ctx,points,ref,kind,core_index=None):
    if kind=='monitoring':return float(np.linalg.norm(np.diff(np.asarray(points[:core_index+1]),axis=0),axis=1).sum())
    if kind=='close_observation':
        area={'type':'Circle','center_m':ref['observation_point_enu_m'][:2],'radius_m':30.}
    else:area=ctx.zones['alert' if kind=='feint' else 'protected']['geometry']
    total=0.
    for a,b in zip(points,points[1:]):
        a,b=np.asarray(a),np.asarray(b);length=float(np.linalg.norm(b-a))
        if float(geometry_facts(area,a)['signed_distance_m'])<=0:return total
        if length==0:continue
        intervals=geometry_facts(area,a,line_direction=(b-a)/length)['line_intervals_m']
        hits=[max(0.,lo) for lo,hi in intervals if hi>=0 and lo<=length]
        if hits:return total+min(hits)
        total+=length
    return math.inf


class RadialFormationPlanner:
    legacy_vertical_slice=False
    kind=None
    def plan(self,scene,group,params):return self.plan_with_template(scene,group,params)[0]

    def plan_with_template(self,scene,group,params):
        if 'candidate_budget' in params:
            from .candidate_search import plan_continuous_group
            return plan_continuous_group(scene,group,params)
        from .role_planners import PlanningInfeasible
        ctx=Context(scene,group,params)
        candidates=[];reasons=defaultdict(int)
        base=ctx.rng.uniform(0,2*math.pi)
        angles=[base+k*2*math.pi/24 for k in range(24)];ctx.rng.shuffle(angles)
        for angle in angles:
            if not bearing_allowed(angle,params):
                reasons['same_target_work_area_bearing']+=1
                continue
            result,reason=self.attempt(ctx,angle)
            if result is not None:result['angle']=angle
            if result is None:reasons[reason]+=1
            else:
                candidates.append(result)
                if ctx.multi:break
        if not candidates:raise PlanningInfeasible('geometry_infeasible',f'{self.kind}: {dict(reasons)}')
        if ctx.multi:chosen=candidates[0]
        else:
            minimum=min(c['approach_length_m'] for c in candidates)
            pool=[c for c in candidates if c['approach_length_m']<=1.15*minimum]
            chosen=ctx.rng.choice(pool)
            chosen['template']['direction_selection']={'minimum_approach_length_m':minimum,
                'selected_approach_length_m':chosen['approach_length_m'],'maximum_ratio':1.15,
                'feasible_candidates':len(candidates),'eligible_candidates':len(pool),
                'selection_order':'role constraints -> 115% route-length filter -> private random direction -> corridor'}
        # Candidate previews establish constraints and planned route costs.
        # The selected direction alone generates the final shared geometry.
        selection=chosen['template'].get('direction_selection')
        selected_angle=chosen['angle']
        chosen,failure=self.attempt(ctx,selected_angle)
        if chosen is None:raise PlanningInfeasible('geometry_infeasible',failure)
        if selection is not None:chosen['template']['direction_selection']=selection
        chosen['template']['formation_split']={'numeric_slot':ctx.slot,'members':ctx.split,'shared_between_timing_versions':True}
        chosen['template']['work_area_bearing_deg']=math.degrees(selected_angle)%360
        return RouteBundle(chosen['routes'],{a:0. for a in group['members']}),chosen['template']

    def attempt(self,ctx,angle):
        from .warning_approach import warning_ingress, deploy_inside_warning
        members=ctx.group['members'];routes={};refs={};score=0.
        spacing=float(ctx.family['lateral_spacing_m'])
        operation=getattr(ctx,'operation_parameters',{})
        radius=max(12.,1.1*max(ctx.speed**2/3.75,math.sqrt(ctx.speed**3/14.)))
        if self.kind=='close_observation':
            spacing=max(spacing,2*radius+25.)
            clearance=ctx.zones['alert']['offset_m']+operation.get('observation_alert_clearance_m',70.)
        elif self.kind=='feint':
            clearance=(ctx.zones['alert']['offset_m']+ctx.zones['protected']['offset_m'])/2
        else:clearance=ctx.zones['protected']['offset_m']-operation.get('intrusion_endpoint_depth_m',30.)
        ingress,failure=warning_ingress(ctx,angle,spacing)
        if failure:return None,failure
        blocks=ingress['blocks']
        for side,stock in enumerate(ctx.split):
            relative=getattr(ctx,'relative_bearings_rad',[i*math.pi for i in range(len(ctx.split))])
            work_angle=getattr(ctx,'work_angle',angle)+relative[side]
            outward=np.array([math.cos(work_angle),math.sin(work_angle)])
            direction=-outward;normal=np.array([-direction[1],direction[0]])
            entry_blocks=defaultdict(list)
            for a in stock:entry_blocks[ctx.states[a].get('entry_id','none')].append(a)
            ordered=sorted(entry_blocks.values(),key=lambda agents:float(np.mean([ctx.starts[a] for a in agents],axis=0)@normal))
            layouts=[]
            for agents in ordered:
                actual_mean=np.mean([ctx.starts[a] for a in agents],axis=0)
                inward,_=start_line(ctx.scene,actual_mean);first_normal=np.array([-inward[1],inward[0]])
                entry_id=ctx.states[agents[0]].get('entry_id','none')
                all_entry=[np.asarray(s['position_enu_m'][:2]) for s in ctx.states.values() if s.get('entry_id','none')==entry_id]
                anchor_mean=np.mean(all_entry,axis=0);scale=spacing/ctx.family['lateral_spacing_m']
                virtual={a:ctx.starts[a]+(scale-1)*float((ctx.starts[a]-anchor_mean)@first_normal)*first_normal for a in agents}
                mean=np.mean(list(virtual.values()),axis=0)
                offsets={a:float((virtual[a]-mean)@first_normal) for a in agents}
                half=max(abs(x) for x in offsets.values())
                layouts.append((agents,virtual,offsets,half))
            widths=[2*l[3] for l in layouts];whole=sum(widths)+spacing*(len(widths)-1)
            cursor=-whole/2+getattr(ctx,'station_lateral_shift_m',0.)
            for agents,virtual,offsets,half in layouts:
                hcenter=cursor+half;cursor+=2*half+spacing
                for a in agents:
                    h=hcenter+offsets[a]
                    member_clearance=clearance
                    if self.kind=='feint' and operation:
                        fraction=operation['feint_depth_fraction_by_agent'][a]
                        member_clearance=ctx.zones['alert']['offset_m']-fraction*(ctx.zones['alert']['offset_m']-ctx.zones['protected']['offset_m'])
                    station=contour_point(ctx.geometry,ctx.center,outward,member_clearance,-h)
                    if station is None:return None,'exact_station_unavailable'
                    hover=self.kind=='close_observation' and operation.get('observation_dwell_method')=='hover'
                    target=station+(radius*outward if self.kind=='close_observation' and not hover else 0.)
                    points=list(ingress['routes'][a])
                    branch=deploy_inside_warning(ctx,points[-1],target)
                    if branch is None:return None,'inside_warning_station_deployment_unavailable'
                    points.extend(branch[1:])
                    ref={'retreat_required':self.kind!='intrusion','formation_lane':ingress['references'][a]}
                    if self.kind=='close_observation':
                        # Disjoint small circles around independent exact observation points.
                        # A sparse circuit remains inside the observation disk without
                        # per-corner slowdown dominating its dwell duration.
                        # Actual dwell is still measured from exported truth.
                        alpha=math.atan2(outward[1],outward[0]);steps=6
                        ring=[station+radius*np.array([math.cos(alpha+k*2*math.pi/steps),math.sin(alpha+k*2*math.pi/steps)])
                              for k in range(1,steps+1)]
                        if operation:
                            from .operation_parameters import dwell_circle
                            ring=[] if hover else dwell_circle(station,outward,radius,ctx.speed,operation['planned_observation_dwell_s'])
                        points+=ring
                        ref['observation_point_enu_m']=[*station.tolist(),ctx.altitude]
                        ref['planned_observation_dwell_s']=operation.get('planned_observation_dwell_s',24.)
                        if operation:ref['observation_dwell_method']=operation['observation_dwell_method']
                    if self.kind!='intrusion':
                        end=ctx.retreat(points[-1],outward)
                        if end is None:return None,'all-warning-exterior_retreat_unavailable'
                        departure=ctx.planner().path(points[-1].tolist(),end.tolist())
                        if departure is None:return None,'retreat_route_unavailable'
                        points.extend(np.asarray(p) for p in departure[1:]);ref['retreat_warning_clearance_m']=ctx.retreat_warning_minimum_m
                    else:end=station
                    try:points=[np.asarray(p) for p in clean_route([p.tolist() for p in points],ctx.planner())]
                    except ValueError:return None,'lane_full_route_invalid'
                    if not ctx.route_valid(points):return None,'exact_role_policy_or_restriction_clearance'
                    if hover:
                        index=int(np.argmin(np.linalg.norm(np.asarray(points)-station,axis=1)))
                        if not 0<index<len(points)-1 or np.linalg.norm(points[index]-station)>1e-6:
                            return None,'hover_station_lost_during_route_cleaning'
                        ref['intermediate_dwell']={'waypoint_index':index,'duration_s':operation['planned_observation_dwell_s']}
                    ref['endpoint_enu_m']=[*end.tolist(),ctx.altitude]
                    score+=core_path_length(ctx,points,ref,self.kind)
                    if self.kind=='feint':
                        ref['planned_depth_point_enu_m']=[*station.tolist(),ctx.altitude]
                        ref['planned_turn_point_enu_m']=[*station.tolist(),ctx.altitude]
                    routes[a]=[[*p.tolist(),ctx.altitude] for p in points];refs[a]=ref
        endpoints=np.array([refs[a]['endpoint_enu_m'] for a in members])
        minimum=min(float(np.linalg.norm(endpoints[i]-endpoints[j])) for i,j in __import__('itertools').combinations(range(len(members)),2))
        if minimum<(15. if ctx.speed>7 else 6.):return None,'independent_endpoint_spacing'
        work_spacing={}
        if operation and self.kind in ('close_observation','feint'):
            from .operation_parameters import work_point_spacing
            work_spacing=work_point_spacing(refs,self.kind,ctx.speed)
            for name,check in work_spacing.items():
                if not check['valid']:return None,'independent_'+name+'_spacing'
        template={'role':ctx.role,'execution_method':ctx.group['execution_method'],'target_id':ctx.group['target_id'],
                  'planning_version':VERSION,'references':refs,'formation':{'blocks':blocks},
                  'retreat_warning_minimum_m':ctx.retreat_warning_minimum_m,
                  'planning_minimum_endpoint_spacing_m':minimum}
        if operation:template['planning_work_point_spacing']=work_spacing
        if self.kind=='close_observation':
            planned_dwell=operation.get('planned_observation_dwell_s',24.)
            template['close_observation']={'observation_radius_m':30.,'planned_dwell_s':planned_dwell,'minimum_dwell_s':planned_dwell*4/5,
                                           'approach_mode':ctx.params['approach_mode']}
        elif self.kind=='feint':template['feint']={'retreat_distance_tolerance_m':5.,'retreat_drop_fraction_max':.1,
                                                 'approach_mode':ctx.params['approach_mode']}
        else:template.update(required_intrusion_depth_m=20.,intrusion_endpoint_min_spacing_m=15. if ctx.speed>7 else 6.)
        return {'routes':routes,'template':template,'approach_length_m':score},None


class CloseObservationPlanner(RadialFormationPlanner):kind='close_observation'
class FeintPlanner(RadialFormationPlanner):kind='feint'
class IntrusionPlanner(RadialFormationPlanner):kind='intrusion'

class MonitoringPlanner(RadialFormationPlanner):
    kind='monitoring'
    def attempt(self,ctx,angle):
        reasons=defaultdict(int)
        phase_variants=4
        for candidate_index in range(ctx.params.get('monitor_radius_start_index',0)*phase_variants,32*phase_variants):
            radius_index,phase_variant=divmod(candidate_index,phase_variants)
            result,reason=self._attempt_radius(ctx,angle,radius_index,phase_variant)
            if result is None:
                reasons[reason]+=1
                if reason=='closed_orbit_cannot_clear_exact_restrictions_and_alert_policy':break
                continue
            preview=self._nominal_interval(ctx,result)
            if any(preview[mode]['below_warning'] for mode in ('synchronous','sequential')):
                reasons['nominal_paired_interval_too_close']+=1
                continue
            result['template']['planning_nominal_interval']=preview
            return result,None
        return None,str(dict(reasons))

    def _nominal_interval(self,ctx,result):
        from task_v07.execution import departure_delays
        from .geometry_checks import planning_layer_interval_check
        from .pipeline import COMMON_CONSTANTS
        template=result['template']
        skeleton={**COMMON_CONSTANTS,'members':ctx.group['members'],
            'column_seed':ctx.params.get('column_seed',ctx.params['planning_seed'])}
        nominal={}
        for a,points in result['routes'].items():
            xy=np.asarray(points)[:,:2]
            entry=np.asarray(template['references'][a]['planned_orbit_entry_enu_m'][:2])
            core_index=int(np.argmin(np.linalg.norm(xy-entry,axis=1)))
            distance=core_path_length(ctx,xy,{},'monitoring',core_index)
            nominal[a]=20.+distance/ctx.speed
        plans=departure_delays(skeleton,nominal)
        bundle=RouteBundle(result['routes'],{a:0. for a in ctx.group['members']})
        report=planning_layer_interval_check(bundle,plans,ctx.speed)
        report['basis']='nominal planning candidate only; actual delays come from independent single flights'
        return report

    def _attempt_radius(self,ctx,angle,radius_index,phase_variant=0):
        from .monitoring_deployment import monitoring_candidate
        geometry=ctx.geometry
        extent=(geometry['radius_m'] if geometry['type']=='Circle' else
                float(np.linalg.norm(np.asarray(geometry['vertices_m'])-ctx.center,axis=1).max()))
        low=extent+ctx.zones['alert']['offset_m']+10.
        # Preserve the original permitted radius range; duration is diagnostic only.
        radii=np.arange(low,extent+ctx.zones['warning']['offset_m']-35.,20.)[radius_index:]
        r=None
        for candidate in radii:
            samples=ctx.center+candidate*np.c_[np.cos(np.linspace(0,2*math.pi,129)),np.sin(np.linspace(0,2*math.pi,129))]
            distances=geometry_facts(geometry,samples)['signed_distance_m']
            if np.any(distances<=ctx.zones['alert']['offset_m']+5.) or np.any(distances>=ctx.zones['warning']['offset_m']-5.):continue
            if ctx.route_valid(samples):r=float(candidate);break
        if r is None:return None,'closed_orbit_cannot_clear_exact_restrictions_and_alert_policy'
        return monitoring_candidate(ctx,angle,r,phase_variant)
