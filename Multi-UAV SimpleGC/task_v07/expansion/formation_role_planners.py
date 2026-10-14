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
        self.facility,self.zones=zones_of(scene,group['target_id'])
        self.geometry=self.facility['geometry'];self.center=np.asarray(center_of(self.geometry))
        self.states={s['agent_id']:s for s in self.family['initial_states']}
        self.starts={a:np.asarray(self.states[a]['position_enu_m'][:2],float) for a in group['members']}
        self.multi=params['approach_mode']=='multi_direction'
        self.slot=params.get('geometry_slot',0)
        self.split=stable_split(self.family,group['members'],self.slot,self.multi)
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
                elif warnings and entity.get('layer')=='warning':
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
        for distance in np.arange(100.,3500.,25.):
            q=np.asarray(point)+distance*outward
            if (check_retreat_point(self.scene,q)['valid'] and
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
        from .role_planners import PlanningInfeasible
        ctx=Context(scene,group,params)
        candidates=[];reasons=defaultdict(int)
        base=ctx.rng.uniform(0,2*math.pi)
        angles=[base+k*2*math.pi/24 for k in range(24)];ctx.rng.shuffle(angles)
        for angle in angles:
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
        chosen,failure=self.attempt(ctx,chosen['angle'])
        if chosen is None:raise PlanningInfeasible('geometry_infeasible',failure)
        if selection is not None:chosen['template']['direction_selection']=selection
        chosen['template']['formation_split']={'numeric_slot':ctx.slot,'members':ctx.split,'shared_between_timing_versions':True}
        return RouteBundle(chosen['routes'],{a:0. for a in group['members']}),chosen['template']

    def attempt(self,ctx,angle):
        members=ctx.group['members'];routes={};refs={};blocks=[];score=0.
        spacing=float(ctx.family['lateral_spacing_m'])
        radius=max(12.,1.1*max(ctx.speed**2/3.75,math.sqrt(ctx.speed**3/14.)))
        if self.kind=='close_observation':
            spacing=max(spacing,2*radius+25.)
            clearance=ctx.zones['alert']['offset_m']+70.
        elif self.kind=='feint':
            clearance=(ctx.zones['alert']['offset_m']+ctx.zones['protected']['offset_m'])/2
        else:clearance=ctx.zones['protected']['offset_m']-30.
        for side,stock in enumerate(ctx.split):
            outward=np.array([math.cos(angle+side*math.pi),math.sin(angle+side*math.pi)])
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
            cursor=-whole/2
            for agents,virtual,offsets,half in layouts:
                hcenter=cursor+half;cursor+=2*half+spacing
                margin=35.+1.5*half+2.
                origin=ctx.center+hcenter*normal
                # contour_point uses its own left normal of outward (= -normal).
                station_center=contour_point(ctx.geometry,ctx.center,outward,clearance,-hcenter)
                if station_center is None:return None,'station_block_does_not_fit'
                target_center=station_center+(radius*outward if self.kind=='close_observation' else 0.)
                lead=ctx.lead(origin,outward,margin,half)
                if lead is None:return None,'all-warning-exterior_collection_unavailable'
                corridor,failure=shared_reference_corridor(ctx.scene,agents,virtual,lead,target_center,
                    ctx.planner(margin,warnings=True),ctx.planner(),
                    form_up_depths=(max(100.,2*half+50.),100.,150.,200.,60.))
                if failure:return None,failure
                try: corridor['reference']=[np.asarray(p) for p in clean_route([p.tolist() for p in corridor['reference']],ctx.planner())]
                except ValueError:return None,'reference_leg_invalid'
                for a in agents:
                    lane=offset_polyline(corridor['reference'],offsets[a])
                    if lane is None:return None,'offset_lane_swallowtail'
                    h=hcenter+offsets[a]
                    station=contour_point(ctx.geometry,ctx.center,outward,clearance,-h)
                    if station is None:return None,'exact_station_unavailable'
                    lane[-1]=station+(radius*outward if self.kind=='close_observation' else 0.)
                    points=[ctx.starts[a],*lane[1:]]
                    ref={'retreat_required':self.kind!='intrusion','formation_lane':{'side':side,
                        'lane_offset_m':offsets[a],'collection_point_enu_m':[*lead.tolist(),ctx.altitude]}}
                    if self.kind=='close_observation':
                        # Disjoint small circles around independent exact observation points.
                        # A sparse circuit remains inside the observation disk without
                        # per-corner slowdown dominating its dwell duration.
                        # Actual dwell is still measured from exported truth.
                        alpha=math.atan2(outward[1],outward[0]);steps=6
                        ring=[station+radius*np.array([math.cos(alpha+k*2*math.pi/steps),math.sin(alpha+k*2*math.pi/steps)])
                              for k in range(1,steps+1)]
                        points+=ring
                        ref['observation_point_enu_m']=[*station.tolist(),ctx.altitude]
                        ref['planned_observation_dwell_s']=24.
                    if self.kind!='intrusion':
                        end=ctx.retreat(points[-1],outward)
                        if end is None:return None,'all-warning-exterior_retreat_unavailable'
                        departure=ctx.planner().path(points[-1].tolist(),end.tolist())
                        if departure is None:return None,'retreat_route_unavailable'
                        points.extend(np.asarray(p) for p in departure[1:]);ref['retreat_warning_clearance_m']=210.
                    else:end=station
                    try:points=[np.asarray(p) for p in clean_route([p.tolist() for p in points],ctx.planner())]
                    except ValueError:return None,'lane_full_route_invalid'
                    if not ctx.route_valid(points):return None,'exact_role_policy_or_restriction_clearance'
                    ref['endpoint_enu_m']=[*end.tolist(),ctx.altitude]
                    score+=core_path_length(ctx,points,ref,self.kind)
                    if self.kind=='feint':
                        ref['planned_depth_point_enu_m']=[*station.tolist(),ctx.altitude]
                        ref['planned_turn_point_enu_m']=[*station.tolist(),ctx.altitude]
                    routes[a]=[[*p.tolist(),ctx.altitude] for p in points];refs[a]=ref
                blocks.append({'side':side,'members':sorted(agents),'half_width_m':half,'shared_route_margin_m':margin,
                               'collection_point_enu_m':[*lead.tolist(),ctx.altitude]})
        endpoints=np.array([refs[a]['endpoint_enu_m'] for a in members])
        minimum=min(float(np.linalg.norm(endpoints[i]-endpoints[j])) for i,j in __import__('itertools').combinations(range(len(members)),2))
        if minimum<(15. if ctx.speed>7 else 6.):return None,'independent_endpoint_spacing'
        template={'role':ctx.role,'execution_method':ctx.group['execution_method'],'target_id':ctx.group['target_id'],
                  'planning_version':VERSION,'references':refs,'formation':{'blocks':blocks},
                  'planning_minimum_endpoint_spacing_m':minimum}
        if self.kind=='close_observation':
            template['close_observation']={'observation_radius_m':30.,'planned_dwell_s':24.,'minimum_dwell_s':19.2,
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
        phase_variants=4 if ctx.multi else 1
        for candidate_index in range(32*phase_variants):
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
        geometry=ctx.geometry
        extent=(geometry['radius_m'] if geometry['type']=='Circle' else
                float(np.linalg.norm(np.asarray(geometry['vertices_m'])-ctx.center,axis=1).max()))
        low=extent+ctx.zones['alert']['offset_m']+10.
        radii=np.arange(low,extent+ctx.zones['warning']['offset_m']-35.,20.)[radius_index:]
        role_planner=ctx.planner();r=None
        for candidate in radii:
            samples=ctx.center+candidate*np.c_[np.cos(np.linspace(0,2*math.pi,129)),np.sin(np.linspace(0,2*math.pi,129))]
            distances=geometry_facts(geometry,samples)['signed_distance_m']
            if np.any(distances<=ctx.zones['alert']['offset_m']+5.) or np.any(distances>=ctx.zones['warning']['offset_m']-5.):continue
            if ctx.route_valid(samples):r=float(candidate);break
        if r is None:return None,'closed_orbit_cannot_clear_exact_restrictions_and_alert_policy'
        phases={}
        for side,stock in enumerate(ctx.split):
            outward=np.array([math.cos(angle+side*math.pi),math.sin(angle+side*math.pi)])
            travel_normal=np.array([outward[1],-outward[0]])
            inward,_=start_line(ctx.scene,np.mean([ctx.starts[a] for a in stock],axis=0))
            first_normal=np.array([-inward[1],inward[0]])
            if ctx.multi:
                values=[angle+side*math.pi+((j+.5)/len(stock)-.5)*math.pi for j in range(len(stock))]
            else:values=[angle+2*math.pi*j/len(stock) for j in range(len(stock))]
            # Preserve lane order when fanning out to independent orbit phases.
            ordered_agents=sorted(stock,key=lambda a:(float(ctx.starts[a]@first_normal),a))
            ordered_phases=sorted(values,key=lambda phi:float(np.array([math.cos(phi),math.sin(phi)])@travel_normal))
            phases.update(zip(ordered_agents,ordered_phases))
        phase_diagnostic=None
        if ctx.multi:
            from .monitoring_phases import shared_phase_candidates
            if not hasattr(self,'_phase_cache'):self._phase_cache={}
            key=(ctx.params.get('geometry_seed',ctx.params['planning_seed']),r,tuple(sorted(ctx.group['members'])))
            if key not in self._phase_cache:self._phase_cache[key]=shared_phase_candidates(ctx,r)
            phase_diagnostic=self._phase_cache[key][phase_variant]
            if phase_diagnostic['estimated_max_interval_s']>phase_diagnostic['allowed_interval_s']:
                return None,'nominal_revisit_geometry_infeasible'
            phases={a:angle+value for a,value in phase_diagnostic['phases'].items()}
        # Same direction needs parallel final approaches to every distinct phase.
        common_direction=np.array([-math.cos(angle),-math.sin(angle)])
        parallel_leads={}
        if not ctx.multi:
            for a,phi in phases.items():
                entry=ctx.center+r*np.array([math.cos(phi),math.sin(phi)])
                lead=entry-150.*common_direction
                if not role_planner.visible(lead.tolist(),entry.tolist()):
                    return None,'same_direction_parallel_phase_entries_do_not_fit'
                parallel_leads[a]=lead
        routes={};refs={};blocks=[];score=0.
        laps=2+(seed_for(ctx.family.get('sampling_seed',0),f'monitoring-laps-slot:{ctx.slot}')%2)
        # Bound the polygon sagitta to 10m; dense tiny corners unnecessarily
        # slow the frozen continuous-route tracker at every original node.
        steps=max(24,int(math.ceil(math.pi/math.acos(1.-min(10./r,1.)))))
        rotation=1. if seed_for(ctx.family.get('sampling_seed',0),f'monitoring-clock-slot:{ctx.slot}')%2 else -1.
        # Keep all approach legs outside the observable orbit tube.  The final
        # tangent lead enters that tube in the same geometry at every phase.
        approach_scene={'world':ctx.scene['world'],'entities':[
            {'type':'hard_constraint_obstacle','geometry':g} for g in role_planner.obstacles]}
        approach_scene['entities'].append({'type':'hard_constraint_obstacle',
            'geometry':{'type':'Circle','center_m':ctx.center.tolist(),'radius_m':r+40.}})
        approach_planner=ExactVisibilityPlanner(approach_scene,0.)
        tangent_length=math.sqrt((r+50.)**2-r*r)
        for side,stock in enumerate(ctx.split):
            outward=np.array([math.cos(angle+side*math.pi),math.sin(angle+side*math.pi)])
            sub=defaultdict(list)
            for a in stock:sub[ctx.states[a].get('entry_id','none')].append(a)
            for agents in sub.values():
                mean=np.mean([ctx.starts[a] for a in agents],axis=0)
                inward,_=start_line(ctx.scene,mean);normal=np.array([-inward[1],inward[0]])
                offsets={a:float((ctx.starts[a]-mean)@normal) for a in agents}
                half=max(abs(o) for o in offsets.values());margin=35.+1.5*half+2.
                lead=ctx.lead(ctx.center,outward,margin+100.,half)
                if lead is None:return None,'monitoring_collection_unavailable'
                tail=lead-75.*outward
                corridor,failure=shared_reference_corridor(ctx.scene,agents,ctx.starts,lead,tail,
                    ctx.planner(margin,warnings=True),role_planner,
                    form_up_depths=(max(100.,2*half+50.),100.,150.,200.,60.))
                if failure:return None,failure
                try: corridor['reference']=[np.asarray(p) for p in clean_route([p.tolist() for p in corridor['reference']],ctx.planner())]
                except ValueError:return None,'reference_leg_invalid'
                for a in agents:
                    lane=offset_polyline(corridor['reference'],offsets[a])
                    if lane is None:return None,'monitoring_lane_swallowtail'
                    points=[ctx.starts[a],*lane[1:]]
                    phi=phases[a];entry=ctx.center+r*np.array([math.cos(phi),math.sin(phi)])
                    tangent=rotation*np.array([-math.sin(phi),math.cos(phi)])
                    target=entry-tangent_length*tangent if ctx.multi else parallel_leads[a]
                    branch=approach_planner.path(points[-1].tolist(),target.tolist())
                    if branch is None:return None,'orbit_phase_approach_unavailable'
                    points.extend(np.asarray(p) for p in branch[1:])
                    points.append(entry)
                    core_index=len(points)-1
                    ring=[ctx.center+r*np.array([math.cos(phi+rotation*k*2*math.pi/steps),math.sin(phi+rotation*k*2*math.pi/steps)])
                          for k in range(1,steps*laps+1)]
                    points.extend(ring)
                    # Exit tangent, then outwards: avoid returning across the orbit.
                    tangent=rotation*np.array([-math.sin(phi),math.cos(phi)])
                    exit_lead=points[-1]+tangent_length*tangent
                    if role_planner.visible(points[-1].tolist(),exit_lead.tolist()):points.append(exit_lead)
                    retreat=None
                    for delta in (0.,math.pi/6,-math.pi/6,math.pi/3,-math.pi/3,math.pi/2,-math.pi/2,math.pi):
                        retreat=ctx.retreat(points[-1],np.array([math.cos(phi+delta),math.sin(phi+delta)]))
                        if retreat is not None and approach_planner.path(points[-1].tolist(),retreat.tolist()) is not None:break
                        retreat=None
                    if retreat is None:return None,'monitoring_retreat_unavailable'
                    departure=approach_planner.path(points[-1].tolist(),retreat.tolist())
                    if departure is None:return None,'monitoring_retreat_route_unavailable'
                    points.extend(np.asarray(p) for p in departure[1:])
                    try: points=[np.asarray(p) for p in clean_route([p.tolist() for p in points],role_planner)]
                    except ValueError:return None,'monitoring_route_leg_invalid'
                    if not ctx.route_valid(points):return None,'monitoring_full_route_policy_or_clearance'
                    score+=core_path_length(ctx,points,{},self.kind,core_index)
                    routes[a]=[[*p.tolist(),ctx.altitude] for p in points]
                    refs[a]={'endpoint_enu_m':[*retreat.tolist(),ctx.altitude],'retreat_required':True,
                        'retreat_warning_clearance_m':210.,'planned_orbit_entry_enu_m':[*entry.tolist(),ctx.altitude],
                        'planned_orbit_phase_rad':phi,'orbit_tangent_lead_enu_m':[*target.tolist(),ctx.altitude],'formation_lane':{'side':side,'lane_offset_m':offsets[a]}}
                blocks.append({'side':side,'members':sorted(agents),'half_width_m':half,
                    'shared_route_margin_m':margin,'collection_point_enu_m':[*lead.tolist(),ctx.altitude]})
        template={'role':'monitoring','execution_method':'monitoring','target_id':ctx.group['target_id'],
            'planning_version':VERSION,'references':refs,'formation':{'blocks':blocks},
            'phase_geometry_estimate':phase_diagnostic,
            'monitoring':{'orbit_center_enu_m':ctx.center.tolist(),'orbit_radius_m':r,
                         'track_tolerance_m':30.,'effective_speed_min_m_s':.5,'min_loop_duration_s':5.,
                         'planned_laps':float(laps),'rotation_sign':rotation,'approach_mode':ctx.params['approach_mode']}}
        return {'routes':routes,'template':template,'approach_length_m':score},None
