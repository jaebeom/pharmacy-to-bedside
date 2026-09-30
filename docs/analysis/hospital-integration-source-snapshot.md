# 병원 통합 작업의 임시 소스 보존

2026-09-22 작업 중 저장소 밖에 만들어진 실행·모델링·진단 스크립트의 원문 스냅샷이다.

**실행 지침이나 완성된 런타임이 아니다.** 일부는 실행 중인 Isaac 세션의 전역 변수와 절대 경로에 의존하며, 실패한 시도도 포함한다. 최종 제품 경로는 `sim/standalone/`과 조제기 모델 폴더다. 이 보존본을 그대로 실행하지 않는다. 기존 알고리즘 통합 완료를 뜻하지 않는다.


## p3_add_rail_robot.py

원본: `/tmp/p3_add_rail_robot.py` · SHA-256 `08b6f29fb505c92f8c59557335fa4052a81711ad84e7a1d85e31f9ed2e0d2b38`

```python

import sys
sys.path.insert(0,'/home/rokey/ROKEY_P3_A3/sim/standalone')
from p3sim import scene as p3scene,layout as p3layout
from pxr import UsdPhysics
origin=(-5.8,10.25,0.0);stroke=6.4;ylimits=(-.25,.45);zlimits=(0.,1.10)
armroot='/World/P3RailM0609'
robotfile='/home/rokey/cobot3_ws/isaacpjt/M0609/Collected_m0609_gripper/m0609_gripper.usd'
a_root,robot_prim,joints=p3scene.build_xy_rail_with_robot(s,armroot,robotfile,origin,stroke,ylimits,.05,.25,[1e7,1e5,1e8],z_limits=zlimits)
p3scene.ensure_link_visuals(s,robot_prim,('base_link','link_1','link_2','link_3','link_4','link_5','link_6'),print)
# Reuse the existing scene's paired fixed X guides, with the longer measured span.
for part in p3layout.rail_boxes(origin,stroke,ylimits,.05,.25):
 c=UsdGeom.Cube.Define(s,armroot+'/FixedTracks/'+part.name);c.CreateSizeAttr(1);c.CreateDisplayColorAttr([Gf.Vec3f(*part.color)])
 xf=UsdGeom.Xformable(c);xf.AddTranslateOp().Set(Gf.Vec3d(*part.center));xf.AddScaleOp().Set(Gf.Vec3f(*part.size))
# Raise lift and mounted arm together for a clear static review, without running physics.
lift=.45
for name in ['Rail/CarriageZ','Mount']:
 prim=s.GetPrimAtPath(armroot+'/'+name)
 for xop in UsdGeom.Xformable(prim).GetOrderedXformOps():
  if xop.GetOpType()==UsdGeom.XformOp.TypeTranslate:
   pos=Gf.Vec3d(xop.Get());pos[2]+=lift;xop.Set(pos)
j=UsdPhysics.PrismaticJoint(s.GetPrimAtPath(armroot+'/Rail/rail_z'));UsdPhysics.DriveAPI.Get(j.GetPrim(),'linear').GetTargetPositionAttr().Set(lift)
# No simulation play: this is a layout proposal and not a motion validation.
s.GetPrimAtPath(armroot).SetCustomDataByKey('review_status','STATIC_LAYOUT_ONLY_MOTION_UNVALIDATED')
op=UsdGeom.Xformable(s.GetPrimAtPath('/P3ReviewCamera')).GetOrderedXformOps()[0]
camera([-5.95,2.6,4.4],[-5.95,11.1,1.0])
out=Path('/home/rokey/markle_tmp/m2-pr483-view')
s.GetSessionLayer().Export(str(out/'dispenser-rail-m0609-review-layer.usda'))
layer=Sdf.Layer.CreateNew(str(out/'hospital-v2-dispenser-rail-m0609.usda'));layer.subLayerPaths=[str(out/'dispenser-rail-m0609-review-layer.usda'),source];layer.Save()
report={'rail_origin':origin,'x_stroke':stroke,'y_limits':ylimits,'z_limits':zlimits,'display_lift':lift,'robot_base_height':.70,'robot_asset':robotfile,'joint_names':list(joints),'fixed_rail_x_extent':[-9.2,-2.4],'conveyor_rightmost_x':-9.5275,'static_x_clearance_to_conveyor':.3275,'motion_and_collision_validation':'NOT RUN','color_decor':'deferred by user; existing asset colors retained'}
(out/'rail-m0609-layout-review.json').write_text(json.dumps(report,indent=2))
print('RAIL_M0609_REVIEW_READY',json.dumps(report),flush=True)


```


## p3_align_rail.py

원본: `/tmp/p3_align_rail.py` · SHA-256 `627ec6fad6168114fb4b92efebc5f442b169c25cf81eaf4b69c3a14b163763fa`

```python

from pxr import UsdPhysics
s.RemovePrim('/World/P3RailM0609')
origin=(-5.8,10.75,0.0);stroke=6.4;ylimits=(-.1,.33);zlimits=(0.,1.1)
a_root,robot_prim,joints=p3scene.build_xy_rail_with_robot(s,'/World/P3RailM0609',robotfile,origin,stroke,ylimits,.05,.25,[1e7,1e5,1e8],z_limits=zlimits)
p3scene.ensure_link_visuals(s,robot_prim,('base_link','link_1','link_2','link_3','link_4','link_5','link_6'),print)
for part in p3layout.rail_boxes(origin,stroke,ylimits,.05,.25):
 c=UsdGeom.Cube.Define(s,a_root+'/FixedTracks/'+part.name);c.CreateSizeAttr(1);c.CreateDisplayColorAttr([Gf.Vec3f(*part.color)])
 xf=UsdGeom.Xformable(c);xf.AddTranslateOp().Set(Gf.Vec3d(*part.center));xf.AddScaleOp().Set(Gf.Vec3f(*part.size))
results=json.loads(Path('/tmp/p3-reach-results.json').read_text())
sol=next(r['solution'] for r in results if r['origin_y']==10.75 and r['target']=='module')
rx,ry,rz=sol['rail']
for name,shift in [('Rail/CarriageX',(rx,0,0)),('Rail/CarriageY',(rx,ry,0)),('Rail/CarriageZ',(rx,ry,rz)),('Mount',(rx,ry,rz))]:
 for xo in UsdGeom.Xformable(s.GetPrimAtPath(a_root+'/'+name)).GetOrderedXformOps():
  if xo.GetOpType()==UsdGeom.XformOp.TypeTranslate:xo.Set(Gf.Vec3d(xo.Get())+Gf.Vec3d(*shift))
for jname,val in zip(['rail_x','rail_y','rail_z'],[rx,ry,rz]):UsdPhysics.DriveAPI.Get(s.GetPrimAtPath(a_root+'/Rail/'+jname),'linear').GetTargetPositionAttr().Set(val)
# Apply the solved module insertion configuration statically using USD joint frames.
q=sol['joints'][1]
def jointframe(j,idx):
 pos=j.GetAttribute('physics:localPos'+str(idx)).Get() or Gf.Vec3f(0)
 quat=j.GetAttribute('physics:localRot'+str(idx)).Get() or Gf.Quatf(1)
 return Gf.Matrix4d().SetRotate(Gf.Quatd(quat))*Gf.Matrix4d().SetTranslate(Gf.Vec3d(pos))
js={p.GetName():p for p in Usd.PrimRange(s.GetPrimAtPath(robot_prim)) if p.IsA(UsdPhysics.RevoluteJoint)}
for i,angle in enumerate(q,1):
 j=js['joint_'+str(i)];b0=s.GetPrimAtPath(j.GetRelationship('physics:body0').GetTargets()[0]);b1=s.GetPrimAtPath(j.GetRelationship('physics:body1').GetTargets()[0])
 cache=UsdGeom.XformCache();w0=cache.GetLocalToWorldTransform(b0)
 axis=j.GetAttribute('physics:axis').Get();vec={'X':Gf.Vec3d(1,0,0),'Y':Gf.Vec3d(0,1,0),'Z':Gf.Vec3d(0,0,1)}[axis]
 rot=Gf.Matrix4d().SetRotate(Gf.Rotation(vec,math.degrees(angle)))
 w1=jointframe(j,1).GetInverse()*rot*jointframe(j,0)*w0
 par=cache.GetLocalToWorldTransform(b1.GetParent())
 xf=UsdGeom.Xformable(b1);xf.ClearXformOpOrder();xf.AddTransformOp(opSuffix='reachReview').Set(w1*par.GetInverse())
 UsdPhysics.DriveAPI.Get(j,'angular').GetTargetPositionAttr().Set(math.degrees(angle))
cache=UsdGeom.XformCache();link=s.GetPrimAtPath(robot_prim+'/link_6')
tcp=cache.GetLocalToWorldTransform(link).Transform(Gf.Vec3d(0,0,.19671))
target=sol['points'][1][1];err=(tcp-Gf.Vec3d(*target)).GetLength()
report={'comparison':results,'usd_static_tcp':list(tcp),'module_insert_target':target,'usd_tcp_error_m':err,'scope':'static nominal IK + USD frame cross-check; collision/path execution not validated','emptyworld_matched':{'y_limits':ylimits,'z_limits':zlimits,'carriage_height':.25,'tcp_offset':.19671},'x_stroke_changed_for_hospital':6.4}
out=Path('/home/rokey/markle_tmp/m2-pr483-view')
(out/'rail-reach-validation.json').write_text(json.dumps(report,indent=2))
s.GetSessionLayer().Export(str(out/'dispenser-rail-m0609-review-layer.usda'))
op=UsdGeom.Xformable(s.GetPrimAtPath('/P3ReviewCamera')).GetOrderedXformOps()[0]
camera([-6.3,3.5,3.6],[-6.3,11.0,1.0])
print('ALIGNED_REACH_RESULT',json.dumps({'tcp':list(tcp),'target':target,'error_m':err}),flush=True)


```


## p3_amr_inspect.py

원본: `/tmp/p3_amr_inspect.py` · SHA-256 `f1568115c92b13d83fac8938dc0deabc84cfd9f1fd3e253fdca220ce4fb9f9c5`

```python

import hashlib
amr_old=s.GetPrimAtPath('/World/ridgeback_ur5')
amr_cache=UsdGeom.XformCache()
amr_data={p:{'position':list(amr_cache.GetLocalToWorldTransform(s.GetPrimAtPath('/World/ridgeback_ur5/'+p)).ExtractTranslation()),'matrix':str(amr_cache.GetLocalToWorldTransform(s.GetPrimAtPath('/World/ridgeback_ur5/'+p)))} for p in ['base_link','ur_arm_shoulder_link']}
amr_data['references']=str(amr_old.GetMetadata('references'))
(out/'amr-before.json').write_text(json.dumps(amr_data,indent=2))
print('AMR_BEFORE',amr_data,flush=True)


```


## p3_asset_final_view.py

원본: `/tmp/p3_asset_final_view.py` · SHA-256 `8ef1170e2d8ccef09f47076143f1520b991da0b77097e6fc4b5c95c919fdd9e6`

```python

from isaacsim import SimulationApp
app=SimulationApp({'headless':False,'width':1400,'height':900})
import json,math
from pathlib import Path
from pxr import Usd,UsdGeom,Gf,Sdf,UsdLux
exec(compile(Path('/tmp/p3_package_asset.py').read_text(),'/tmp/p3_package_asset.py','exec'))
import omni.usd
from omni.kit.viewport.utility import get_active_viewport
omni.usd.get_context().open_stage('/tmp/p3-dispenser-pr/src/rokey_p3_description/models/dispenser/dispenser.usdc')
for _ in range(30):app.update()
s=omni.usd.get_context().get_stage();s.SetEditTarget(s.GetSessionLayer())
cam=UsdGeom.Camera.Define(s,'/ReviewCamera');cam.CreateFocalLengthAttr(24);cam.CreateHorizontalApertureAttr(24)
m=Gf.Matrix4d();m.SetLookAt(Gf.Vec3d(0,-5,2.6),Gf.Vec3d(0,0,1.1),Gf.Vec3d(0,0,1))
UsdGeom.Xformable(cam).AddTransformOp().Set(m.GetInverse());get_active_viewport().camera_path='/ReviewCamera'
l=UsdLux.DomeLight.Define(s,'/ReviewLight');l.CreateIntensityAttr(1000)
print('FINAL_ASSET_VIEW_READY',flush=True)
while app.is_running():app.update()
app.close()


```


## p3_attach_inlets.py

원본: `/tmp/p3_attach_inlets.py` · SHA-256 `b63b9edb1b7f824b97c18650683a7f54b875129971028a2aa83f10d8a1db99ea`

```python

from pxr import Vt
out=Path('/home/rokey/markle_tmp/m2-pr483-view')
front=11.26546546
s.RemovePrim('/World/P3ProposedInlets')
parent=s.GetPrimAtPath('/World/P3ProposedInlets')
for p in parent.GetChildren():
 xf=UsdGeom.Xformable(p)
 tr=next(o for o in xf.GetOrderedXformOps() if o.GetOpType()==UsdGeom.XformOp.TypeTranslate)
 v=Gf.Vec3d(tr.Get())
 if p.GetName().startswith('Pill'):
  v[0]+=-8.05-(-7.805662751258908)
  v[1]+=11.115-(10.743905423164177)
 elif p.GetName().startswith('Module'):
  v[0]+=-7.70-(-7.305662751258908)
  v[1]+=front-10.923905423164177
 tr.Set(v)
# Set support rear edge 5 mm into the cabinet, leaving no floating gap.
p=s.GetPrimAtPath('/World/P3ProposedInlets/PillSupport')
for op in UsdGeom.Xformable(p).GetOrderedXformOps():
 if op.GetOpType()==UsdGeom.XformOp.TypeTranslate:op.Set(Gf.Vec3d(-8.05,front-.115,.83))
 if op.GetOpType()==UsdGeom.XformOp.TypeScale:op.Set(Gf.Vec3f(.22,.24,.04))
def inletbox(name,c,size,color):
 g=UsdGeom.Cube.Define(s,'/World/P3ProposedInlets/'+name);g.CreateSizeAttr(1);g.CreateDisplayColorAttr([Gf.Vec3f(*color)])
 xf=UsdGeom.Xformable(g);xf.ClearXformOpOrder();xf.AddTranslateOp().Set(Gf.Vec3d(*c));xf.AddScaleOp().Set(Gf.Vec3f(*size))
inletbox('PillMountPlate',(-8.05,front-.0025,.875),(.24,.015,.16),(.48,.52,.56))
inletbox('ModuleMountPlate',(-7.70,front-.0025,1.02),(.15,.015,.23),(.48,.52,.56))
# Confirm that each mount overlaps the real front wall, and all inlet meshes fit the body width.
bc=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render])
checks={}
for name in ['PillSupport','PillMountPlate','ModuleBack','ModuleMountPlate']:
 b=bc.ComputeWorldBound(s.GetPrimAtPath('/World/P3ProposedInlets/'+name)).ComputeAlignedRange()
 assert b.GetMin()[1]<front and b.GetMax()[1]>=front-1e-6,name
 assert b.GetMin()[0]>-10.1853 and b.GetMax()[0]<-7.3852,name
 checks[name]={'min':list(b.GetMin()),'max':list(b.GetMax()),'front_wall_overlap':True}
s.GetSessionLayer().Export(str(out/'dispenser-remodeled-geometry.usda'))
# Flatten only the dispenser and accessories into a standalone asset.
flat=s.Flatten();asset=Usd.Stage.CreateNew(str(out/'dispenser-remodeled-standalone.usdc'))
r=UsdGeom.Xform.Define(asset,'/Dispenser');asset.SetDefaultPrim(r.GetPrim());UsdGeom.SetStageUpAxis(asset,UsdGeom.Tokens.z);UsdGeom.SetStageMetersPerUnit(asset,1)
UsdGeom.Xformable(r).AddTranslateOp().Set(Gf.Vec3d(8.78522324,-11.7254655,0))
mapping={'/World/machine':'/Dispenser/Machine','/World/P3ProposedInlets':'/Dispenser/Inlets','/World/P3DispenserRemodel':'/Dispenser/Remodel'}
for a,b in mapping.items():Sdf.CopySpec(flat,a,asset.GetRootLayer(),b)
def remap(path):
 for a,b in mapping.items():
  if path.HasPrefix(Sdf.Path(a)):return path.ReplacePrefix(Sdf.Path(a),Sdf.Path(b))
 return path
for p in asset.Traverse():
 for rel in p.GetRelationships():
  ts=rel.GetTargets()
  if ts:rel.SetTargets([remap(t) for t in ts])
 for attr in p.GetAttributes():
  cs=attr.GetConnections()
  if cs:attr.SetConnections([remap(t) for t in cs])
r.GetPrim().SetAssetInfoByKey('name','P3 remodeled dispenser with attached inlets')
asset.GetRootLayer().Save()
reopened=Usd.Stage.Open(str(out/'dispenser-remodeled-standalone.usdc'));assert reopened.GetDefaultPrim()
report={'front_wall_y':front,'pill_center_x':-8.05,'module_center_x':-7.70,'mount_checks':checks,'standalone_reopen':'PASS','physics_IK':'NOT RUN','git_upload':'not yet published; asset dependency review pending'}
(out/'inlet-attachment-validation.json').write_text(json.dumps(report,indent=2))
camera([-8.75,6.5,2.4],[-8.75,11.5,1.25])
print('INLETS_ATTACHED_AND_ASSET_EXPORTED',json.dumps(report),flush=True)


```


## p3_audit_asset.py

원본: `/tmp/p3_audit_asset.py` · SHA-256 `26e206372cbb39631bcf72682c3ccbe4f64ccc6b773b7f93e5d39906c61041a8`

```python

from pxr import UsdUtils
p='/home/rokey/markle_tmp/m2-pr483-view/dispenser-remodeled-standalone.usdc'
a=Usd.Stage.Open(p)
a.GetRootLayer().Export('/tmp/p3-dispenser-audit.usda')
issues=[];assets=[]
for prim in a.Traverse():
 for rel in prim.GetRelationships():
  for t in rel.GetTargets():
   if not a.GetObjectAtPath(t):issues.append([str(rel.GetPath()),str(t)])
 for attr in prim.GetAttributes():
  if attr.GetTypeName()==Sdf.ValueTypeNames.Asset:
   v=attr.Get()
   if v:assets.append([str(attr.GetPath()),v.path,v.resolvedPath])
Path('/tmp/p3-dispenser-audit.json').write_text(json.dumps({'dangling_targets':issues,'assets':assets,'prims':len(list(a.Traverse()))},indent=2))
print('ASSET_AUDIT_DONE',flush=True)


```


## p3_belt_detail.py

원본: `/tmp/p3_belt_detail.py` · SHA-256 `94da1d32ab5359c8945a1ffea8f086aa4ac3cae9ca487dfad596935c5383d8f4`

```python

items=[]
bc=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render])
for p in Usd.PrimRange(s.GetPrimAtPath('/World/Conveyor/ConveyorTrack_06'),Usd.TraverseInstanceProxies()):
 if p.IsA(UsdGeom.Mesh):
  b=bc.ComputeWorldBound(p).ComputeAlignedRange();items.append((str(p.GetPath()),list(b.GetMin()),list(b.GetMax())))
Path('/tmp/p3-belt-detail.json').write_text(json.dumps(items))


```


## p3_check_reach.py

원본: `/tmp/p3_check_reach.py` · SHA-256 `17f89405f4a6a63430606aa1be594fe1c50c10f2ea25e6f2a9ff1392c6f45bfe`

```python

import sys,json,math
sys.path.insert(0,'/home/rokey/ROKEY_P3_A3/src/rokey_p3_manipulation')
from rokey_p3_manipulation import scene_v2 as V,m0609_kinematics as K,pick_plan as P
model=K.M0609(K.ToolTransform((0,0,.19671),(0,0,0,1)))
seeds=P.default_seeds((0,0,1.5883,0,1.5778,0),8,seed=1)
params=V.DEFAULT_PARAMS
results=[]
for ry,ylimits in [(10.25,(-.25,.45)),(10.75,(-.10,.33))]:
 sc=V.Scene([],{},[],{},('rail_x','rail_y','rail_z'),((-3.2,3.2),ylimits,(0,1.1)),(-5.8,ry,.25),())
 for kind,point,size in [('round',(-8.05,11.115,.98),(.07,.07,.12)),('module',(-7.70,11.11546546,1.02),(.06,.10,.14))]:
  cell=V.CellV2('test','cylinder' if kind=='round' else 'module','',True,'front',(0,0,1),size)
  target=V.Target(kind,point,(),{})
  _,grip=V.pick_points(cell,params)
  choices=params.rail_round if kind=='round' else [(0,c) for c in params.rail_module]
  solved=None;tried=0
  for yaw,offset in choices:
   pts,ret=V.place_points(cell,target,grip,params,yaw)
   rail=V.rail_for(pts[-1][1],offset,yaw,sc,.05)
   if rail is None:continue
   tried+=1
   pts.append(('retreat',ret))
   targets=[P.Target(n,rail,K.Pose(V.to_base(p,rail,sc),V.tool_quat(yaw))) for n,p in pts]
   for seed in seeds:
    q=P.solve_chain(model,targets,seed)
    if q:
     errors=[math.dist(model.fk(j).position_m,t.pose.position_m) for j,t in zip(q,targets)]
     solved={'rail':rail,'base_world':[a+b for a,b in zip(rail,sc.base_origin)],'yaw':yaw,'joints':q,'points':pts,'max_fk_error':max(errors),'rail_limit_margin':V.rail_margin(rail,sc)};break
   if solved:break
  results.append({'origin_y':ry,'target':kind,'rail_candidates':tried,'solution':solved})
print(json.dumps(results,indent=2))
open('/tmp/p3-reach-results.json','w').write(json.dumps(results,indent=2))


```


## p3_check_reach484.py

원본: `/tmp/p3_check_reach484.py` · SHA-256 `87cc7b70a602dd383378dd93ec614d85d4286d619adf4cf3f386b6a7184a05d7`

```python

import sys,json,math
sys.path.insert(0,'/home/rokey/ROKEY_P3_A3/src/rokey_p3_manipulation')
from rokey_p3_manipulation import scene_v2 as V,m0609_kinematics as K,pick_plan as P
model=K.M0609(K.ToolTransform((0,0,.19671),(0,0,0,1)))
seeds=P.default_seeds((0,0,1.5883,0,1.5778,0),8,seed=1)
params=V.DEFAULT_PARAMS
results=[]
for ry,ylimits in [(10.75,(-.10,.33))]:
 sc=V.Scene([],{},[],{},('rail_x','rail_y','rail_z'),((-5.7,5.7),ylimits,(0,1.1)),(-3.3,ry,.25),())
 for kind,point,size in [('round',(-8.05,11.115,.98),(.07,.07,.12)),('module',(-7.70,11.11546546,1.02),(.06,.10,.14))]:
  cell=V.CellV2('test','cylinder' if kind=='round' else 'module','',True,'front',(0,0,1),size)
  target=V.Target(kind,point,(),{})
  _,grip=V.pick_points(cell,params)
  choices=params.rail_round if kind=='round' else [(0,c) for c in params.rail_module]
  solved=None;tried=0
  for yaw,offset in choices:
   pts,ret=V.place_points(cell,target,grip,params,yaw)
   rail=V.rail_for(pts[-1][1],offset,yaw,sc,.05)
   if rail is None:continue
   tried+=1
   pts.append(('retreat',ret))
   targets=[P.Target(n,rail,K.Pose(V.to_base(p,rail,sc),V.tool_quat(yaw))) for n,p in pts]
   for seed in seeds:
    q=P.solve_chain(model,targets,seed)
    if q:
     errors=[math.dist(model.fk(j).position_m,t.pose.position_m) for j,t in zip(q,targets)]
     solved={'rail':rail,'base_world':[a+b for a,b in zip(rail,sc.base_origin)],'yaw':yaw,'joints':q,'points':pts,'max_fk_error':max(errors),'rail_limit_margin':V.rail_margin(rail,sc)};break
   if solved:break
  results.append({'origin_y':ry,'target':kind,'rail_candidates':tried,'solution':solved})
print(json.dumps(results,indent=2))
open('/home/rokey/markle_tmp/m2-pr484-test/inlet-ik.json','w').write(json.dumps(results,indent=2))


```


## p3_extract_clip.py

원본: `/tmp/p3_extract_clip.py` · SHA-256 `ae49bd99530420f216a9270f33deff0d9178879ce4654a92c9d666e16dc93cbf`

```python

import gi
from pathlib import Path
gi.require_version('Gst','1.0')
from gi.repository import Gst
Gst.init(None)
src='/home/rokey/markle_tmp/m2-amrcombined-lap14/clips/lap14.mkv'
dst='/home/rokey/Documents/P3_발표자료/01_발표영상/04_AMR_첫회배송_180초발췌_통합시뮬_20260921.mp4'
p=Gst.parse_launch(f'filesrc location="{src}" ! decodebin ! videoconvert ! x264enc speed-preset=veryfast bitrate=2500 ! h264parse ! mp4mux ! filesink location="{dst}"')
p.set_state(Gst.State.PAUSED);p.get_state(30*Gst.SECOND)
assert p.seek(1.0,Gst.Format.TIME,Gst.SeekFlags.FLUSH|Gst.SeekFlags.ACCURATE,Gst.SeekType.SET,0,Gst.SeekType.SET,180*Gst.SECOND)
p.set_state(Gst.State.PLAYING)
m=p.get_bus().timed_pop_filtered(Gst.CLOCK_TIME_NONE,Gst.MessageType.EOS|Gst.MessageType.ERROR)
print(m.type)
if m.type==Gst.MessageType.ERROR:print(m.parse_error())
p.set_state(Gst.State.NULL)


```


## p3_find_conveyor.py

원본: `/tmp/p3_find_conveyor.py` · SHA-256 `6ba4534657ddb5dbc624145fb78ee1a9c55b5afaf5071bac57649fb0840a0ec3`

```python

items=[]
bc=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render])
for p in s.Traverse():
 name=str(p.GetPath())
 if any(t in name.lower() for t in ['conveyor','sorter']):
  if p.IsA(UsdGeom.Xform):
   b=bc.ComputeWorldBound(p).ComputeAlignedRange();items.append((name,list(b.GetMin()),list(b.GetMax())))
Path('/tmp/p3-conveyor-bounds.json').write_text(json.dumps(items,indent=2))


```


## p3_finish_attach.py

원본: `/tmp/p3_finish_attach.py` · SHA-256 `283cf914b16a7dd624b2e0f0eb7a515edf6dd0fc169a0d3ef9cf77c6fccaf85d`

```python

op=UsdGeom.Xformable(s.GetPrimAtPath('/P3ReviewCamera')).GetOrderedXformOps()[0]
camera([-8.75,6.5,2.4],[-8.75,11.5,1.25])
s.GetSessionLayer().Export('/home/rokey/markle_tmp/m2-pr483-view/dispenser-remodeled-geometry.usda')
print('ATTACHMENT_FINISHED',flush=True)


```


## p3_inspect_detail.py

원본: `/tmp/p3_inspect_detail.py` · SHA-256 `183c70c233ab1716839d7987d214f5f3b319cdfa3356f4adf42cb042b7c6cc52`

```python

rows=[]
for p in Usd.PrimRange(s.GetPrimAtPath('/World/machine'),Usd.TraverseInstanceProxies()):
 if p.IsInstance():rows.append(('INSTANCE',str(p.GetPath())))
 if p.IsA(UsdGeom.Mesh) and ('ID542/' in str(p.GetPath()) or 'ID307/' in str(p.GetPath())):
  rows.append((str(p.GetPath()),[(a.GetName(),str(a.GetTypeName()),str(a.Get())[:150]) for a in p.GetAttributes()]))
Path('/tmp/p3-machine-detail.json').write_text(json.dumps(rows,indent=2))
camera([-8.75,6.5,2.6],[-8.75,11.55,1.3])


```


## p3_inspect_machine.py

원본: `/tmp/p3_inspect_machine.py` · SHA-256 `e496c0295c81f3fc9c7c0a9e970cd6b66b1bdbc838319380271e23daf38ee1b3`

```python

rows=[]
bc=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render])
for p in Usd.PrimRange(s.GetPrimAtPath('/World/machine'),Usd.TraverseInstanceProxies()):
 if p.IsA(UsdGeom.Mesh):
  b=bc.ComputeWorldBound(p).ComputeAlignedRange();rows.append({'path':str(p.GetPath()),'min':list(b.GetMin()),'max':list(b.GetMax()),'points':len(UsdGeom.Mesh(p).GetPointsAttr().Get() or [])})
Path('/tmp/p3-machine-meshes.json').write_text(json.dumps(rows,indent=2))
print('MESH_INVENTORY',len(rows),flush=True)


```


## p3_intake_closeup.py

원본: `/tmp/p3_intake_closeup.py` · SHA-256 `777ff28239457fa23f3f65c00a79b54677320b723d37c4b3ab9c10972751cad4`

```python

intake_demo.subscription=None
s.RemovePrim('/World/IntakeTrial')
intake_demo=IntakeDemo(s,'/home/rokey/markle_tmp/m2-pr484-test/intake-trial-02')
intake_demo.cases=[('normal','shelf_67_pill'),('normal','shelf_67_module')]
intake_demo.subscribe()
from omni.kit.viewport.utility import get_active_viewport
c=UsdGeom.Camera(s.GetPrimAtPath('/ReviewCamera'));c.CreateFocalLengthAttr(28)
m=Gf.Matrix4d().SetLookAt(Gf.Vec3d(-7.75,9.4,1.55),Gf.Vec3d(-7.9,11.2,1.0),Gf.Vec3d(0,0,1))
UsdGeom.Xformable(c).GetOrderedXformOps()[0].Set(m.GetInverse());get_active_viewport().camera_path='/ReviewCamera'
print('INTAKE_CLOSEUP_TRIAL_STARTED',flush=True)


```


## p3_package_asset.py

원본: `/tmp/p3_package_asset.py` · SHA-256 `5114917743af847606692e01a17780f1ee319daec1c08d6fa570b67c658df298`

```python

from pxr import UsdPhysics
import hashlib
folder=Path('/tmp/p3-dispenser-pr/src/rokey_p3_description/models/dispenser')
a=Usd.Stage.Open('/home/rokey/markle_tmp/m2-pr483-view/dispenser-remodeled-standalone.usdc')
r=a.GetDefaultPrim();cache=UsdGeom.XformCache()
transforms=[(p,cache.GetLocalToWorldTransform(p)) for p in r.GetChildren()]
UsdGeom.Xformable(r).ClearXformOpOrder()
for p,m in transforms:
 p.SetTypeName('Xform');xf=UsdGeom.Xformable(p);xf.ClearXformOpOrder();xf.AddTransformOp(opSuffix='assetLocal').Set(m)
# This is explicitly a visual asset; do not inherit whole-body convex collision across the new hole.
removed=[]
for p in a.Traverse():
 for schema in list(p.GetAppliedSchemas()):
  if 'Physics' in schema or 'Physx' in schema:
   p.RemoveAppliedSchema(schema);removed.append([str(p.GetPath()),schema])
offset=Gf.Vec3d(8.78522324,-11.7254655,0)
anchors={'PillOpening':(-8.05,11.115,.98),'ModuleEntry':(-7.70,11.11546546,1.02),'ConveyorOpening':(-9.8225,11.26546546,1.105)}
for name,point in anchors.items():
 x=UsdGeom.Xform.Define(a,'/Dispenser/Anchors/'+name);x.AddTranslateOp().Set(Gf.Vec3d(*point)+offset)
r.SetCustomDataByKey('validation','VISUAL_ONLY_COLLISION_AND_OPERATION_UNVALIDATED')
file=folder/'dispenser.usdc';a.GetRootLayer().Export(str(file))
b=Usd.Stage.Open(str(file));bc=UsdGeom.BBoxCache(Usd.TimeCode.Default(),['default','render']);bounds=bc.ComputeWorldBound(b.GetDefaultPrim()).ComputeAlignedRange()
assert UsdGeom.Xformable(b.GetDefaultPrim()).GetLocalTransformation()==Gf.Matrix4d(1)
assert not b.GetRootLayer().subLayerPaths
meshes=0
for p in b.Traverse():
 assert not p.HasAuthoredReferences() and not p.HasAuthoredPayloads()
 for rel in p.GetRelationships():
  assert all(b.GetObjectAtPath(t) for t in rel.GetTargets()),str(rel.GetPath())
 if p.IsA(UsdGeom.Mesh):
  meshes+=1;m=UsdGeom.Mesh(p);pts=m.GetPointsAttr().Get();ids=m.GetFaceVertexIndicesAttr().Get();counts=m.GetFaceVertexCountsAttr().Get()
  assert sum(counts)==len(ids) and all(0<=i<len(pts) for i in ids)
source=Path('/home/rokey/assets-from-master01/hospital_custome-20260921/material/etc/Automatic+Blister+Packing+Machine+(DPB-80)/model.usd')
report={'source_commit':'db9d9ada454f9345892a8a488d4704fc22b8864b','source_asset_name':'Automatic Blister Packing Machine (DPB-80)/model.usd','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'asset_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'asset_bytes':file.stat().st_size,'default_prim':'/Dispenser','units':'meters','up_axis':'Z','origin_in_hospital':[-8.78522324,11.7254655,0],'anchors_local':{k:list(Gf.Vec3d(*v)+offset) for k,v in anchors.items()},'bounds_min':list(bounds.GetMin()),'bounds_max':list(bounds.GetMax()),'mesh_count':meshes,'removed_physics_api_count':len(removed),'checks':{'reopen':True,'root_identity':True,'no_external_references':True,'relationship_targets':True,'mesh_indices':True},'not_validated':['collision','watertight_manifold','robot_motion','runtime_hospital_integration'],'source_license':'Original bundled asset license not independently verified; no new license asserted.'}
(folder/'asset.json').write_text(json.dumps(report,indent=2)+'\n')

print('PACKAGED_ASSET_READY',json.dumps(report),flush=True)


```


## p3_pick_ik_probe.py

원본: `/tmp/p3_pick_ik_probe.py` · SHA-256 `5dac93f3eb7be7c007727845748dbabd4b93e0a16c2fb9e40c1010122eb54890`

```python

from isaacsim.robot_motion.motion_generation import LulaKinematicsSolver
import numpy as np
pk_lula=LulaKinematicsSolver(robot_description_path='/home/rokey/cobot3_ws/isaacpjt/M0609/rmpflow/m0609_description.yaml',urdf_path='/home/rokey/cobot3_ws/isaacpjt/M0609/doosan-robot2/urdf/m0609_isaac_sim.urdf')
pk_lula.set_robot_base_pose(np.array([-3.3,10.95,.60]),np.array([1.,0,0,0]))
pk_q=np.array([.70710678,-.70710678,0,0])
pk_results=[]
for pk_y in [11.20,11.49]:
 for pk_z in [.94,1.01]:
  pk_angles,pk_ok=pk_lula.compute_inverse_kinematics('link_6',np.array([-3.3,pk_y-.19671,pk_z]),pk_q)
  pk_results.append({'tcp':[-3.3,pk_y,pk_z],'ok':bool(pk_ok),'joints':pk_angles.tolist()})
(out/'pick-ik-probe.json').write_text(json.dumps(pk_results,indent=2))
print('PICK_IK_PROBE',pk_results,flush=True)


```


## p3_pick_inspect.py

원본: `/tmp/p3_pick_inspect.py` · SHA-256 `83b3e2e2bd9208343fed7cad3a79cc70dec352bc237933731413c79859224f92`

```python

import numpy as np
from pxr import PhysxSchema
from isaacsim.robot_motion.motion_generation import LulaKinematicsSolver
from p3sim.workcell_preview import shelf_surface
pick_inspect={}
pick_inspect['physics_scenes']=[str(p.GetPath()) for p in s.Traverse() if p.IsA(UsdPhysics.Scene)]
pick_inspect['rigid_bodies']=[str(p.GetPath()) for p in s.Traverse() if p.HasAPI(UsdPhysics.RigidBodyAPI)]
pick_inspect['shelf_meshes']=[{'path':str(p.GetPath()),'instance':p.IsInstanceProxy(),'collision':p.HasAPI(UsdPhysics.CollisionAPI)} for p in Usd.PrimRange(s.GetPrimAtPath('/World/Environment/hospital/SM_MedShelf_01d_67'),Usd.TraverseInstanceProxies()) if p.IsA(UsdGeom.Mesh)]
pick_inspect['robot_prims']=[{'path':str(p.GetPath()),'schemas':p.GetAppliedSchemas()} for p in Usd.PrimRange(s.GetPrimAtPath(robot)) if p.HasAPI(UsdPhysics.RigidBodyAPI) or p.IsA(UsdPhysics.Joint)]
(out/'pick-inspect.json').write_text(json.dumps(pick_inspect,indent=2))
print('PICK_INSPECT_READY',flush=True)


```


## p3_pick_ready.py

원본: `/tmp/p3_pick_ready.py` · SHA-256 `3a8ca062fbcaa2035b5ed0aba1891e12cb67c25fbcf2ec7b91755787149019ff`

```python

pr_ready={'objects':{n:b.get_world_pose()[0].tolist() for n,b in pick_trial.objects.items()},'tcp':pick_trial.tcp().tolist(),'joints':pick_trial.robot.get_joint_positions().tolist()}
(out/'pick-ready.json').write_text(json.dumps(pr_ready,indent=2))
pc=UsdGeom.Camera(s.GetPrimAtPath('/ReviewCamera'));pc.CreateFocalLengthAttr(20)
pm=Gf.Matrix4d().SetLookAt(Gf.Vec3d(-3.3,6.7,3.0),Gf.Vec3d(-2.0,11.1,.85),Gf.Vec3d(0,0,1))
UsdGeom.Xformable(pc).GetOrderedXformOps()[0].Set(pm.GetInverse())
print('PICK_READY_POSES',pr_ready,flush=True)


```


## p3_pick_run.py

원본: `/tmp/p3_pick_run.py` · SHA-256 `541aca110bd1e44013cdfcbccc3f5d6a45e8d753725f6b9f2fc2c056619271e8`

```python

exec(compile(Path('/tmp/p3-intake-pr/sim/standalone/p3sim/shelf_pick_trial.py').read_text(), '/tmp/p3-intake-pr/sim/standalone/p3sim/shelf_pick_trial.py','exec'),pickmod.__dict__)
pick_trial.__class__=pickmod.ShelfPickTrial
omni.usd.get_context().get_selection().clear_selected_prim_paths()
pick_trial.run()
print('RANDOM_PICK_RUN_DONE',flush=True)


```


## p3_pick_setup.py

원본: `/tmp/p3_pick_setup.py` · SHA-256 `515d3945d2cce9c02866b9fe741fb277a01691fa60aecf1f394beaecfbd3f5e5`

```python

import types,sys
pickmod=types.ModuleType('p3sim.shelf_pick_trial')
pickmod.__package__='p3sim'
sys.modules[pickmod.__name__]=pickmod
exec(compile(Path('/tmp/p3-intake-pr/sim/standalone/p3sim/shelf_pick_trial.py').read_text(), '/tmp/p3-intake-pr/sim/standalone/p3sim/shelf_pick_trial.py', 'exec'),pickmod.__dict__)
from p3sim.shelf_pick_trial import ShelfPickTrial
intake_demo.subscription=None
pick_trial=ShelfPickTrial(s, '/home/rokey/markle_tmp/m2-hospital-pick3-01',
 '/home/rokey/cobot3_ws/isaacpjt/M0609/doosan-robot2/urdf/m0609_isaac_sim.urdf',
 '/home/rokey/cobot3_ws/isaacpjt/M0609/rmpflow/m0609_description.yaml')
print('RANDOM_PICK_SETUP_DONE',flush=True)


```


## p3_remodel_machine.py

원본: `/tmp/p3_remodel_machine.py` · SHA-256 `568f875e064b12cc1bd3484ff50015d29703ab750bf7bb6b8b0d788f884a5ab9`

```python

# User-requested visual remodeling; all overrides live in the review session.
import math
from pxr import Vt
root=s.GetPrimAtPath('/World/machine')
# Make nested instances editable in the session only.
while True:
 instances=[p for p in Usd.PrimRange(root) if p.IsInstance()]
 if not instances:break
 for p in instances:p.SetInstanceable(False)
xlo,xhi=-10.18522324,-7.38522324
cutlo=(-9.105,11.245,1.3675);cuthi=(-8.440,11.800,1.670)
planes=[(i,1,cutlo[i]) for i in range(3)]+[(i,-1,-cuthi[i]) for i in range(3)]
def clip(poly,axis,sign,value):
 out=[]
 if not poly:return out
 a=poly[-1];da=sign*a[0][axis]-value
 for b in poly:
  db=sign*b[0][axis]-value
  if (da>=-1e-9)!=(db>=-1e-9):
   t=da/(da-db);out.append((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])))
  if db>=-1e-9:out.append(b)
  a,da=b,db
 return out
def subtract(poly):
 remain=poly;outside=[]
 for axis,sign,value in planes:
  q=clip(remain,axis,-sign,-value)
  if len(q)>=3:outside.append(q)
  remain=clip(remain,axis,sign,value)
  if len(remain)<3:break
 return outside
report=[]
cache=UsdGeom.XformCache()
for p in list(Usd.PrimRange(root)):
 if not p.IsA(UsdGeom.Mesh):continue
 mesh=UsdGeom.Mesh(p);pts=mesh.GetPointsAttr().Get();counts=mesh.GetFaceVertexCountsAttr().Get();ids=mesh.GetFaceVertexIndicesAttr().Get()
 mat=cache.GetLocalToWorldTransform(p);inv=mat.GetInverse();world=[mat.Transform(Gf.Vec3d(v)) for v in pts]
 low=[min(v[i] for v in world) for i in range(3)];high=[max(v[i] for v in world) for i in range(3)]
 side=low[0]<xlo-1e-5 or high[0]>xhi+1e-5
 hole=all(high[i]>cutlo[i]+1e-6 and low[i]<cuthi[i]-1e-6 for i in range(3))
 if not (side or hole):continue
 pvdata=[]
 for pv in UsdGeom.PrimvarsAPI(p).GetPrimvars():
  value=pv.ComputeFlattened()
  if value is not None and pv.GetInterpolation()!='constant' and pv.GetPrimvarName()!='normals':pvdata.append((pv,list(value),str(pv.GetInterpolation())))
 newpts=[];newcounts=[];newnorm=[];newpv={str(pv.GetName()):[] for pv,_,_ in pvdata};offset=0
 for fi,n in enumerate(counts):
  face=list(ids[offset:offset+n])
  for j in range(1,n-1):
   corners=[0,j,j+1];tri=[face[k] for k in corners]
   poly=[(world[idx],Gf.Vec3d(*(1 if q==k else 0 for q in range(3)))) for k,idx in enumerate(tri)]
   if side:poly=clip(clip(poly,0,1,xlo),0,-1,-xhi)
   polys=subtract(poly) if hole else [poly]
   for poly in polys:
    for k in range(1,len(poly)-1):
     verts=[poly[0],poly[k],poly[k+1]];loc=[inv.Transform(v[0]) for v in verts]
     normal=Gf.Cross(loc[1]-loc[0],loc[2]-loc[0])
     if normal.GetLength()<1e-8:continue
     normal.Normalize();newcounts.append(3);newpts.extend(Gf.Vec3f(v) for v in loc);newnorm.extend([Gf.Vec3f(normal)]*3)
     for pv,vals,interp in pvdata:
      out=newpv[str(pv.GetName())]
      for _,weights in verts:
       if interp=='uniform':v=vals[fi]
       else:
        sourcevals=[vals[offset+corners[q]] if interp=='faceVarying' else vals[tri[q]] for q in range(3)]
        v=sourcevals[0]*weights[0]+sourcevals[1]*weights[1]+sourcevals[2]*weights[2]
       out.append(v)
  offset+=n
 mesh.GetPointsAttr().Set(newpts);mesh.GetFaceVertexCountsAttr().Set(newcounts);mesh.GetFaceVertexIndicesAttr().Set(list(range(len(newpts))))
 mesh.GetNormalsAttr().Set(newnorm);mesh.SetNormalsInterpolation('faceVarying')
 npv=UsdGeom.PrimvarsAPI(p).GetPrimvar('normals')
 if npv:npv.GetAttr().Block();npv.BlockIndices()
 for pv,_,_ in pvdata:
  pv.Set(newpv[str(pv.GetName())]);pv.SetInterpolation('faceVarying');pv.BlockIndices()
 mesh.GetSubdivisionSchemeAttr().Set('none');mesh.GetDoubleSidedAttr().Set(True)
 mesh.GetExtentAttr().Set(UsdGeom.PointBased.ComputeExtent(newpts) if newpts else [Gf.Vec3f(0),Gf.Vec3f(0)])
 report.append({'path':str(p.GetPath()),'side_trim':side,'aperture_cut':hole,'before_faces':len(counts),'after_faces':len(newcounts),'primvars':[str(v[0].GetName()) for v in pvdata]})
# A real open tunnel with belt floor, steel side reveals and top; no front cover.
def box(name,center,size,color):
 c=UsdGeom.Cube.Define(s,'/World/P3DispenserRemodel/'+name);c.CreateSizeAttr(1)
 xf=UsdGeom.Xformable(c);xf.ClearXformOpOrder();xf.AddTranslateOp().Set(Gf.Vec3d(*center));xf.AddScaleOp().Set(Gf.Vec3f(*size))
 c.CreateDisplayColorAttr([Gf.Vec3f(*color)])
 return c
box('BeltExtension',(-8.7725,11.505,1.3575),(.645,.590,.020),(.075,.09,.10))
box('TunnelLeft',(-9.115,11.5275,1.51875),(.020,.565,.3225),(.42,.45,.48))
box('TunnelRight',(-8.430,11.5275,1.51875),(.020,.565,.3225),(.42,.45,.48))
box('TunnelTop',(-8.7725,11.5275,1.680),(.705,.565,.020),(.42,.45,.48))
box('InnerShadow',(-8.7725,11.810,1.51875),(.665,.015,.3025),(.025,.03,.035))
# Flush side caps cover the clipped sheet ends without recreating protrusions.
for name,x in [('LeftTrimCap',xlo),('RightTrimCap',xhi)]:
 box(name,(x,11.532,1.146),(.006,.318,.522),(.50,.52,.54))
Path('/tmp/p3-remodel-report.json').write_text(json.dumps({'body_x_limits':[xlo,xhi],'aperture_min':cutlo,'aperture_max':cuthi,'modified_meshes':report,'validation':'visual only; collision and robot motion untested'},indent=2))
camera([-8.75,6.5,2.4],[-8.75,11.5,1.25])
s.GetSessionLayer().Export('/tmp/p3-remodeled-session.usda')
print('REMODEL_DONE',len(report),flush=True)


```


## p3_remodel_machine_final.py

원본: `/tmp/p3_remodel_machine_final.py` · SHA-256 `855fd51db1dfab12eb9dda9b3fadc5ff868e60e532d5c9b055fb1f04b5fde794`

```python

# User-requested visual remodeling; all overrides live in the review session.
import math
from pxr import Vt
s.RemovePrim('/World/machine')
s.RemovePrim('/World/P3DispenserRemodel')
root=s.GetPrimAtPath('/World/machine')
# Make nested instances editable in the session only.
while True:
 instances=[p for p in Usd.PrimRange(root) if p.IsInstance()]
 if not instances:break
 for p in instances:p.SetInstanceable(False)
xlo,xhi=-10.18522324,-7.38522324
cutlo=(-10.145,11.245,0.820);cuthi=(-9.500,11.900,1.390)
planes=[(i,1,cutlo[i]) for i in range(3)]+[(i,-1,-cuthi[i]) for i in range(3)]
def clip(poly,axis,sign,value):
 out=[]
 if not poly:return out
 a=poly[-1];da=sign*a[0][axis]-value
 for b in poly:
  db=sign*b[0][axis]-value
  if (da>=-1e-9)!=(db>=-1e-9):
   t=da/(da-db);out.append((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])))
  if db>=-1e-9:out.append(b)
  a,da=b,db
 return out
def subtract(poly):
 remain=poly;outside=[]
 for axis,sign,value in planes:
  q=clip(remain,axis,-sign,-value)
  if len(q)>=3:outside.append(q)
  remain=clip(remain,axis,sign,value)
  if len(remain)<3:break
 return outside
report=[]
cache=UsdGeom.XformCache()
for p in list(Usd.PrimRange(root)):
 if not p.IsA(UsdGeom.Mesh):continue
 mesh=UsdGeom.Mesh(p);pts=mesh.GetPointsAttr().Get();counts=mesh.GetFaceVertexCountsAttr().Get();ids=mesh.GetFaceVertexIndicesAttr().Get()
 mat=cache.GetLocalToWorldTransform(p);inv=mat.GetInverse();world=[mat.Transform(Gf.Vec3d(v)) for v in pts]
 low=[min(v[i] for v in world) for i in range(3)];high=[max(v[i] for v in world) for i in range(3)]
 side=low[0]<xlo-1e-5 or high[0]>xhi+1e-5
 hole=all(high[i]>cutlo[i]+1e-6 and low[i]<cuthi[i]-1e-6 for i in range(3))
 if not (side or hole):continue
 pvdata=[]
 for pv in UsdGeom.PrimvarsAPI(p).GetPrimvars():
  value=pv.ComputeFlattened()
  if value is not None and pv.GetInterpolation()!='constant' and pv.GetPrimvarName()!='normals':pvdata.append((pv,list(value),str(pv.GetInterpolation())))
 newpts=[];newcounts=[];newnorm=[];newpv={str(pv.GetName()):[] for pv,_,_ in pvdata};offset=0
 for fi,n in enumerate(counts):
  face=list(ids[offset:offset+n])
  for j in range(1,n-1):
   corners=[0,j,j+1];tri=[face[k] for k in corners]
   poly=[(world[idx],Gf.Vec3d(*(1 if q==k else 0 for q in range(3)))) for k,idx in enumerate(tri)]
   if side:poly=clip(clip(poly,0,1,xlo),0,-1,-xhi)
   polys=subtract(poly) if hole else [poly]
   for poly in polys:
    for k in range(1,len(poly)-1):
     verts=[poly[0],poly[k],poly[k+1]];loc=[inv.Transform(v[0]) for v in verts]
     normal=Gf.Cross(loc[1]-loc[0],loc[2]-loc[0])
     if normal.GetLength()<1e-8:continue
     normal.Normalize();newcounts.append(3);newpts.extend(Gf.Vec3f(v) for v in loc);newnorm.extend([Gf.Vec3f(normal)]*3)
     for pv,vals,interp in pvdata:
      out=newpv[str(pv.GetName())]
      for _,weights in verts:
       if interp=='uniform':v=vals[fi]
       else:
        sourcevals=[vals[offset+corners[q]] if interp=='faceVarying' else vals[tri[q]] for q in range(3)]
        v=sourcevals[0]*weights[0]+sourcevals[1]*weights[1]+sourcevals[2]*weights[2]
       out.append(v)
  offset+=n
 mesh.GetPointsAttr().Set(newpts);mesh.GetFaceVertexCountsAttr().Set(newcounts);mesh.GetFaceVertexIndicesAttr().Set(list(range(len(newpts))))
 mesh.GetNormalsAttr().Set(newnorm);mesh.SetNormalsInterpolation('faceVarying')
 npv=UsdGeom.PrimvarsAPI(p).GetPrimvar('normals')
 if npv:npv.GetAttr().Block();npv.BlockIndices()
 for pv,_,_ in pvdata:
  pv.Set(newpv[str(pv.GetName())]);pv.SetInterpolation('faceVarying');pv.BlockIndices()
 mesh.GetSubdivisionSchemeAttr().Set('none');mesh.GetDoubleSidedAttr().Set(True)
 mesh.GetExtentAttr().Set(UsdGeom.PointBased.ComputeExtent(newpts) if newpts else [Gf.Vec3f(0),Gf.Vec3f(0)])
 report.append({'path':str(p.GetPath()),'side_trim':side,'aperture_cut':hole,'before_faces':len(counts),'after_faces':len(newcounts),'primvars':[str(v[0].GetName()) for v in pvdata]})
# A real open tunnel with belt floor, steel side reveals and top; no front cover.
def box(name,center,size,color):
 c=UsdGeom.Cube.Define(s,'/World/P3DispenserRemodel/'+name);c.CreateSizeAttr(1)
 xf=UsdGeom.Xformable(c);xf.ClearXformOpOrder();xf.AddTranslateOp().Set(Gf.Vec3d(*center));xf.AddScaleOp().Set(Gf.Vec3f(*size))
 c.CreateDisplayColorAttr([Gf.Vec3f(*color)])
 return c
# Existing ConveyorTrack_06 already continues inside the machine to y=11.8797.
box('TunnelLeft',(-10.155,11.5775,1.105),(.020,.665,.590),(.42,.45,.48))
box('TunnelRight',(-9.490,11.5775,1.105),(.020,.665,.590),(.42,.45,.48))
box('TunnelTop',(-9.8225,11.5775,1.400),(.685,.665,.020),(.42,.45,.48))
box('InnerShadow',(-9.8225,11.925,1.105),(.645,.015,.570),(.025,.03,.035))
# Flush side caps cover the clipped sheet ends without recreating protrusions.
for name,x in [('LeftTrimCap',xlo),('RightTrimCap',xhi)]:
 box(name,(x,11.532,1.146),(.006,.318,.522),(.50,.52,.54))
Path('/tmp/p3-remodel-report.json').write_text(json.dumps({'body_x_limits':[xlo,xhi],'aperture_min':cutlo,'aperture_max':cuthi,'modified_meshes':report,'validation':'visual only; collision and robot motion untested'},indent=2))
camera([-8.75,6.5,2.4],[-8.75,11.5,1.25])
s.GetSessionLayer().Export('/tmp/p3-remodeled-session.usda')
print('REMODEL_DONE',len(report),flush=True)

# Persist the reviewed scene as a separate, reopenable layer.
out=Path('/home/rokey/markle_tmp/m2-pr483-view')
session_path=out/'dispenser-remodeled-geometry.usda'
s.GetSessionLayer().Export(str(session_path))
layer=Sdf.Layer.CreateNew(str(out/'hospital-v2-dispenser-remodeled.usda'))
layer.subLayerPaths=[str(session_path),source]
layer.Save()
# Validate modified topology and the opening in world coordinates.
checks=[]
for r in report:
 mesh=UsdGeom.Mesh(s.GetPrimAtPath(r['path']));pts=mesh.GetPointsAttr().Get();counts=mesh.GetFaceVertexCountsAttr().Get();ids=mesh.GetFaceVertexIndicesAttr().Get()
 assert sum(counts)==len(ids)
 assert all(0<=i<len(pts) for i in ids)
 assert all(math.isfinite(v) for pt in pts for v in pt)
 checks.append(r['path'])
reopened=Usd.Stage.Open(str(out/'hospital-v2-dispenser-remodeled.usda'))
assert reopened and reopened.GetPrimAtPath('/World/P3DispenserRemodel/TunnelTop')
result={'modified_meshes':len(checks),'topology_indices_and_finite_points':'PASS','reopen':'PASS','external_conveyor':'/World/Conveyor/ConveyorTrack_06','opening_min':cutlo,'opening_max':cuthi,'physics_collision_robot_motion':'NOT RUN'}
(out/'dispenser-remodel-validation.json').write_text(json.dumps(result,indent=2))
(out/'dispenser-remodel-report.json').write_text(Path('/tmp/p3-remodel-report.json').read_text())
(out/'remodel_dispenser.py').write_text(Path('/tmp/p3_remodel_machine_final.py').read_text())
print('FINAL_REMODEL_SAVED',json.dumps(result),flush=True)
Path('/tmp/p3-remodel-final-ready').write_text('ready')


```


## p3_replace_amr.py

원본: `/tmp/p3_replace_amr.py` · SHA-256 `fa22ca81eae4eedc3badd8afb5c2956f429907996241820de8234137a776b7d4`

```python

import importlib,hashlib
import p3sim.workcell_preview as workcell_preview
exec(compile(Path('/tmp/p3-intake-pr/sim/standalone/p3sim/workcell_preview.py').read_text(), '/tmp/p3-intake-pr/sim/standalone/p3sim/workcell_preview.py', 'exec'), workcell_preview.__dict__)
amr_asset=Path('/home/rokey/assets-from-master01/hospital_custome-20260921/hopital_custome/Collected_hopital_custome/omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Robots/Clearpath/RidgebackUr/ridgeback_ur5.usd')
amr_report=workcell_preview.build_practice_amr(s,amr_asset)
amr_report['asset']=str(amr_asset)
amr_report['sha256']=hashlib.sha256(amr_asset.read_bytes()).hexdigest()
amr_report['practice31_sha_match']=amr_report['sha256']=='908061d3b9627baa5bb6880acfa8b341d5b322d31e016f639f1fff2e40f85f3e'
(out/'amr-corrected.json').write_text(json.dumps(amr_report,indent=2))
print('PRACTICE_AMR_REPLACED',amr_report,flush=True)


```


## p3_restore_shelf_display.py

원본: `/tmp/p3_restore_shelf_display.py` · SHA-256 `4a14f70f07d7a1d7f1e872673890c31211e32a8e734a6526f137ace94fa6858e`

```python

intake_demo.subscription=None
for name,item in intake_demo.items.items():
 item['move'].Set(Gf.Vec3d(*item['home']));item['turn'].Set(0.)
 UsdGeom.Imageable(item['shape']).MakeVisible()
Path('/home/rokey/markle_tmp/m2-pr484-test/display-reset.json').write_text(json.dumps({'reason':'replenish visual shelf display after completed trials; no production stock change','items':18}))
c=UsdGeom.Camera(s.GetPrimAtPath('/ReviewCamera'));c.CreateFocalLengthAttr(17)
m=Gf.Matrix4d().SetLookAt(Gf.Vec3d(-3.3,-1.5,6.8),Gf.Vec3d(-3.3,11.2,.95),Gf.Vec3d(0,0,1));UsdGeom.Xformable(c).GetOrderedXformOps()[0].Set(m.GetInverse())
s.GetSessionLayer().Export('/home/rokey/markle_tmp/m2-pr484-test/workcell-with-shelf-items.usda')
print('SHELF_DISPLAY_REPLENISHED',flush=True)


```


## p3_review_viewer.py

원본: `/tmp/p3_review_viewer.py` · SHA-256 `832c878bbf6ff5f2517689fa54b90b80b9fa767446f7eb9d3b6e2aa7f72cc7d9`

```python

from isaacsim import SimulationApp
app=SimulationApp({'headless':False,'width':1500,'height':950})
import omni.usd,json,time
from pathlib import Path
from pxr import Usd,UsdGeom,Gf,Sdf
from omni.kit.viewport.utility import get_active_viewport
source='/home/rokey/markle_tmp/m2-pr483-view/hospital-v2-inlets-front-proposal.usda'
omni.usd.get_context().open_stage(source)
for _ in range(120):app.update()
s=omni.usd.get_context().get_stage();s.SetEditTarget(s.GetSessionLayer())
cam=UsdGeom.Camera.Define(s,'/P3ReviewCamera');cam.CreateFocalLengthAttr(24);cam.CreateHorizontalApertureAttr(24)
xf=UsdGeom.Xformable(cam);xf.ClearXformOpOrder();op=xf.AddTransformOp()
def camera(eye,target):
 m=Gf.Matrix4d(1);m.SetLookAt(Gf.Vec3d(*eye),Gf.Vec3d(*target),Gf.Vec3d(0,0,1));op.Set(m.GetInverse());get_active_viewport().camera_path='/P3ReviewCamera'
 cam.GetPrim().CreateAttribute('omni:kit:centerOfInterest',Sdf.ValueTypeNames.Vector3d).Set(Gf.Vec3d(0,0,-(Gf.Vec3d(*eye)-Gf.Vec3d(*target)).GetLength()))
 print('CAMERA_APPLIED',eye,target,'up=Z',flush=True)
camera([-6.8,4.0,3.1],[-6.8,11.5,1.2])
bc=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render]);rows=[]
for p in Usd.PrimRange(s.GetPrimAtPath('/World/machine')):
 if p.IsA(UsdGeom.Mesh):
  b=bc.ComputeWorldBound(p).ComputeAlignedRange();rows.append({'path':str(p.GetPath()),'min':list(b.GetMin()),'max':list(b.GetMax()),'points':len(UsdGeom.Mesh(p).GetPointsAttr().Get() or [])})
Path('/tmp/p3-machine-meshes.json').write_text(json.dumps(rows,indent=2))
print('REVIEW_READY meshes=',len(rows),flush=True)
last=None
while app.is_running():
 app.update()
 p=Path('/tmp/p3-review-command.json')
 if p.exists() and p.stat().st_mtime_ns!=last:
  last=p.stat().st_mtime_ns
  try:
   cmd=json.loads(p.read_text())
   if 'script' in cmd:
    exec(compile(Path(cmd['script']).read_text(),cmd['script'],'exec'),globals())
   if 'eye' in cmd:camera(cmd['eye'],cmd['target'])
   for path in cmd.get('hide',[]):
    assert path.startswith('/World/machine/')
    prim=s.GetPrimAtPath(path);assert prim
    UsdGeom.Imageable(prim).MakeInvisible();print('HIDDEN',path,flush=True)
   for path in cmd.get('show',[]):
    assert path.startswith('/World/machine/')
    UsdGeom.Imageable(s.GetPrimAtPath(path)).MakeVisible()
   if cmd.get('save_session'):s.GetSessionLayer().Export('/tmp/p3-review-session.usda')
  except Exception as e:print('COMMAND_ERROR',repr(e),flush=True)
app.close()


```


## p3_shelf_bounds.py

원본: `/tmp/p3_shelf_bounds.py` · SHA-256 `69f806d3e4db3936811cc3e48c969d0e88178e6a5303bd9a2b54bda90194cfed`

```python

rows=[]
bc=UsdGeom.BBoxCache(Usd.TimeCode.Default(),['default','render'])
for p in s.Traverse():
 if any(v in p.GetName().lower() for v in ['shelf','shelve']):
  b=bc.ComputeWorldBound(p).ComputeAlignedRange();rows.append([str(p.GetPath()),list(b.GetMin()),list(b.GetMax())])
Path('/tmp/p3-shelf-bounds.json').write_text(json.dumps(rows))


```


## p3_shelf_surfaces.py

원본: `/tmp/p3_shelf_surfaces.py` · SHA-256 `cc8670fcbc46065d2562a1bdcc6cab76efc297121633948f2f565d970efaa836`

```python

from pxr import Usd,UsdGeom,Gf
from collections import defaultdict
s=Usd.Stage.Open('/home/rokey/markle_tmp/m2-pr484-test/hospital-pr484-resolved.usda');cache=UsdGeom.XformCache();levels=defaultdict(float)
p=s.GetPrimAtPath('/World/Environment/hospital/SM_MedShelf_01d_67')
for m in Usd.PrimRange(p,Usd.TraverseInstanceProxies()):
 if not m.IsA(UsdGeom.Mesh):continue
 mesh=UsdGeom.Mesh(m);mat=cache.GetLocalToWorldTransform(m);points=[mat.Transform(Gf.Vec3d(v)) for v in mesh.GetPointsAttr().Get()];idx=mesh.GetFaceVertexIndicesAttr().Get();k=0
 for n in mesh.GetFaceVertexCountsAttr().Get():
  face=[points[i] for i in idx[k:k+n]];k+=n
  if n<3:continue
  z=sum(v[2] for v in face)/n
  if .15<z<1.85 and max(v[2] for v in face)-min(v[2] for v in face)<.001:
   for j in range(1,n-1):
    cross=Gf.Cross(face[j]-face[0],face[j+1]-face[0])
    if cross[2]>0:levels[round(z,3)]+=cross[2]/2
print(sorted((z,a) for z,a in levels.items() if a>.08))


```


## p3_start_intake.py

원본: `/tmp/p3_start_intake.py` · SHA-256 `fcf9a49ae2db5b8b4c173b9515f67be91a12c4e375e2a6720ef97d59e2cfe58b`

```python

import p3sim
p3sim.__path__.insert(0,'/tmp/p3-intake-pr/sim/standalone/p3sim')
from p3sim.workcell_preview import IntakeDemo
import omni.timeline
omni.timeline.get_timeline_interface().stop()
intake_demo=IntakeDemo(s,'/home/rokey/markle_tmp/m2-pr484-test/intake-trial-01').subscribe()
print('INTAKE_TRIAL_STARTED items=18 cases=22 mode=KINEMATIC_FIXTURE',flush=True)


```


## p3_stop_review_physics.py

원본: `/tmp/p3_stop_review_physics.py` · SHA-256 `284abffe94c2537f974ac612a9cfe1732a52118b55308008236f64669aa5835d`

```python

import omni.timeline
omni.timeline.get_timeline_interface().stop()
print('REVIEW_PHYSICS_STOPPED',flush=True)


```


## p3_test484.py

원본: `/tmp/p3_test484.py` · SHA-256 `1c807dae0521b2674253125f63def940539939eec63576b62c981303c1fe531d`

```python

from isaacsim import SimulationApp
app=SimulationApp({'headless':False,'width':1440,'height':900})
import sys,json,time,math
from pathlib import Path
from pxr import Usd,UsdGeom,UsdPhysics,UsdLux,Gf,Sdf
import omni.usd,omni.timeline
from omni.kit.viewport.utility import get_active_viewport
sys.path.insert(0,'/tmp/p3-pr486-followup/sim/standalone')
from p3sim import scene,layout
out=Path('/home/rokey/markle_tmp/m2-pr484-test')
source=out/'hospital-pr484-resolved.usda'
omni.usd.get_context().open_stage(str(source))
for _ in range(100):app.update()
s=omni.usd.get_context().get_stage();bc=UsdGeom.BBoxCache(Usd.TimeCode.Default(),['default','render']);xc=UsdGeom.XformCache()
def bbox(p):
 b=bc.ComputeWorldBound(p).ComputeAlignedRange();return {'min':list(b.GetMin()),'max':list(b.GetMax())}
shelves=[]
for i in range(67,76):
 p=s.GetPrimAtPath('/World/Environment/hospital/SM_MedShelf_01d_'+str(i));assert p and p.IsActive(),i
 shelves.append({'path':str(p.GetPath()),'world_translate':list(xc.GetLocalToWorldTransform(p).ExtractTranslation()),'bounds':bbox(p)})
conveyors=[{'path':str(p.GetPath()),'bounds':bbox(p)} for p in s.GetPrimAtPath('/World/Conveyor').GetChildren() if p.IsActive() and p.GetName().startswith('ConveyorTrack')]
clock=[str(p.GetPath()) for p in s.Traverse() if 'clock' in p.GetName().lower() or 'ROS2PublishClock' in str(p.GetAttribute('node:type').Get())]
errors=[str(e) for e in s.GetRootLayer().GetExternalReferences() if False] # composition warnings audited from viewer log
doors={n:s.GetPrimAtPath('/World/Environment/hospital/'+n).IsActive() for n in ['SM_Door_01b6','SM_Door_01b7','SM_Door_01b8','Geo_M_DoorFrame51','Geo_M_DoorFrame53']}
report={'source_commit':'db9d9ada454f9345892a8a488d4704fc22b8864b','shelves':shelves,'conveyors':conveyors,'clock_prims':clock,'composition_errors':errors,'doors_active':doors,'machine_before':bbox(s.GetPrimAtPath('/World/machine')),'physics':'NOT RUN'}
(out/'baseline-check.json').write_text(json.dumps(report,indent=2))
print('BASELINE_CHECK',json.dumps({'shelves':len(shelves),'conveyors':len(conveyors),'clock':len(clock),'composition_errors':len(errors),'doors':doors}),flush=True)
# Isolated overlay: do not edit the #484 source or its source assets.
layer=Sdf.Layer.CreateNew(str(out/'hospital-pr484-dispenser-rail.usda'));layer.subLayerPaths=[str(source)];layer.Save();s.GetRootLayer().subLayerPaths if False else None
s.SetEditTarget(s.GetSessionLayer())
s.GetPrimAtPath('/World/machine').SetActive(False)
d=UsdGeom.Xform.Define(s,'/World/ReviewedDispenser');d.GetPrim().GetReferences().AddReference('/tmp/p3-dispenser-pr/src/rokey_p3_description/models/dispenser/dispenser.usdc');d.AddTranslateOp().Set(Gf.Vec3d(-8.78522324,11.7254655,0))
origin=(-3.30,10.75,0);stroke=11.4;ylim=(-.10,.33);zlim=(0,1.1)
armroot,robot,joints=scene.build_xy_rail_with_robot(s,'/World/ReviewRailM0609','/home/rokey/cobot3_ws/isaacpjt/M0609/Collected_m0609_gripper/m0609_gripper.usd',origin,stroke,ylim,.05,.25,[1e7,1e5,1e8],z_limits=zlim)
scene.ensure_link_visuals(s,robot,('base_link','link_1','link_2','link_3','link_4','link_5','link_6'),print)
for part in layout.rail_boxes(origin,stroke,ylim,.05,.25):
 c=UsdGeom.Cube.Define(s,armroot+'/Tracks/'+part.name);c.CreateSizeAttr(1);c.CreateDisplayColorAttr([Gf.Vec3f(*part.color)]);xf=UsdGeom.Xformable(c);xf.AddTranslateOp().Set(Gf.Vec3d(*part.center));xf.AddScaleOp().Set(Gf.Vec3f(*part.size))
# Display the arm in its default folded pose with raised lift; physics remains stopped.
for name in ['Rail/CarriageZ','Mount']:
 for op in UsdGeom.Xformable(s.GetPrimAtPath(armroot+'/'+name)).GetOrderedXformOps():
  if op.GetOpType()==UsdGeom.XformOp.TypeTranslate:
   pos=Gf.Vec3d(op.Get());pos[2]+=.45;op.Set(pos)
cam=UsdGeom.Camera.Define(s,'/ReviewCamera');cam.CreateFocalLengthAttr(20);cam.CreateHorizontalApertureAttr(24)
m=Gf.Matrix4d();m.SetLookAt(Gf.Vec3d(-3.3,0,6.5),Gf.Vec3d(-3.3,11.2,.9),Gf.Vec3d(0,0,1));UsdGeom.Xformable(cam).AddTransformOp().Set(m.GetInverse());get_active_viewport().camera_path='/ReviewCamera'
omni.usd.get_context().get_selection().clear_selected_prim_paths()
s.GetSessionLayer().Export(str(out/'integration-overrides.usda'));layer.subLayerPaths=[str(out/'integration-overrides.usda'),str(source)];layer.Save()
(out/'layout.json').write_text(json.dumps({'rail_origin':origin,'x_stroke':stroke,'y_limits':ylim,'z_limits':zlim,'track_x_bounds':[-9.2,2.6],'shelf_count':len(shelves),'review_only':True},indent=2))
print('PR484_INTEGRATION_READY',flush=True)
last=None
while app.is_running():
 app.update()
 p=out/'command.json'
 if p.exists() and p.stat().st_mtime_ns!=last:
  last=p.stat().st_mtime_ns
  try:exec(compile(Path(json.loads(p.read_text())['script']).read_text(),'<review-command>','exec'),globals())
  except Exception as e:print('REVIEW_COMMAND_ERROR',repr(e),flush=True)
app.close()


```


## propose_inlets.py

원본: `/home/rokey/markle_tmp/m2-pr483-view/propose_inlets.py` · SHA-256 `ce834570e0c197feeff35640035ef4c026c13b531b18195d9be36a6c3bf67dc2`

```python

from isaacsim import SimulationApp
app=SimulationApp({'headless':False,'width':1500,'height':950})
import omni.usd,math,json
from pathlib import Path
from pxr import Usd,UsdGeom,Gf,Sdf
from isaacsim.core.utils.viewports import set_camera_view
root=Path('/home/rokey/markle_tmp/m2-pr483-view')
base=root/'hospital-v2-main-321c069-display.usda'
overlay=root/'hospital-v2-inlets-front-proposal.usda'
layer=Sdf.Layer.CreateNew(str(overlay));layer.subLayerPaths=[str(base)];layer.Save()
omni.usd.get_context().open_stage(str(overlay))
for _ in range(120):app.update()
stage=omni.usd.get_context().get_stage();stage.SetEditTarget(stage.GetRootLayer())
prim=stage.GetPrimAtPath('/World/machine');assert prim
bb=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render],useExtentsHint=False).ComputeWorldBound(prim).ComputeAlignedRange()
lo,hi=bb.GetMin(),bb.GetMax();front=float(hi[0]);cy=float((lo[1]+hi[1])/2)
parent='/World/P3ProposedInlets';UsdGeom.Xform.Define(stage,parent)
def box(name,c,size,color,yaw=0):
 g=UsdGeom.Cube.Define(stage,parent+'/'+name);g.CreateSizeAttr(1);g.CreateDisplayColorAttr([Gf.Vec3f(*color)])
 x=UsdGeom.Xformable(g);x.AddTranslateOp().Set(Gf.Vec3d(*c))
 if yaw:x.AddRotateZOp().Set(yaw)
 x.AddScaleOp().Set(Gf.Vec3f(*size));g.GetPrim().SetCustomDataByKey('status','PROPOSED_VISUAL_ONLY_IK_COLLISION_UNVALIDATED')
blue=(.08,.38,.95);purple=(.7,.15,.9);grey=(.6,.65,.7)
fy=float(lo[1]);x=front-.95;y=fy-.18;floor=.85;wall=.01;h=.12;r=.065
box('PillSupport',(x,fy-.1,floor-.02),(.22,.32,.04),grey)
box('PillFloor',(x,y,floor+.005),(.14,.14,.01),blue)
for i in range(32):
 a=2*math.pi*i/32
 box('PillRim%02d'%i,(x+r*math.cos(a),y+r*math.sin(a),floor+.01+h/2),(.01,2*math.pi*r/32*1.08,h),blue,a*180/math.pi)
# Existing module opening 0.08 m horizontal, 0.16 m vertical, depth 0.15 m.
mx=front-.45;mz=1.02;depth=.15;w=.08;hh=.16;t=.018;my=fy-depth
box('ModuleBack',(mx,fy-.005,mz),(w+2*t,.01,hh+2*t),purple)
for suffix,dx in [('Left',-(w+t)/2),('Right',(w+t)/2)]:box('Module'+suffix,(mx+dx,fy-depth/2,mz),(t,depth,hh+2*t),purple)
for suffix,dz in [('Bottom',-(hh+t)/2),('Top',(hh+t)/2)]:box('Module'+suffix,(mx,fy-depth/2,mz+dz),(w,depth,t),purple)
box('ModuleInterior',(mx,fy-.011,mz),(w,.006,hh),(.025,.025,.035))
report={'status':'proposal, visual only; no collision, IK or operation validation','source_commit':'321c069','machine_bound_min':list(lo),'machine_bound_max':list(hi),'pill':{'opening_center':[x,y,floor+.01+h],'inner_diameter':.12,'floor_z':floor+.01,'insert_axis':[0,0,-1]},'module':{'entry_center':[mx,my,mz],'opening_width':w,'opening_height':hh,'depth':depth,'insert_axis':[0,1,0]},'rationale':'existing v2 inlet dimensions and elevations retained; -Y front face, right half near shelves; visually selected to avoid conveyor outlet','unchanged':'original machine, shelf, door and rail geometry; only proposed inlet overlay added'}
(root/'inlet-proposal.json').write_text(json.dumps(report,indent=2));stage.GetRootLayer().Save()
set_camera_view(eye=[front+1.5,fy-4.2,2.7],target=[front-.65,fy,1.05],camera_prim_path='/OmniverseKit_Persp')
print('INLET_PROPOSAL_READY '+json.dumps(report),flush=True)
while app.is_running():app.update()
app.close()


```


## remodel_dispenser.py

원본: `/home/rokey/markle_tmp/m2-pr483-view/remodel_dispenser.py` · SHA-256 `855fd51db1dfab12eb9dda9b3fadc5ff868e60e532d5c9b055fb1f04b5fde794`

```python

# User-requested visual remodeling; all overrides live in the review session.
import math
from pxr import Vt
s.RemovePrim('/World/machine')
s.RemovePrim('/World/P3DispenserRemodel')
root=s.GetPrimAtPath('/World/machine')
# Make nested instances editable in the session only.
while True:
 instances=[p for p in Usd.PrimRange(root) if p.IsInstance()]
 if not instances:break
 for p in instances:p.SetInstanceable(False)
xlo,xhi=-10.18522324,-7.38522324
cutlo=(-10.145,11.245,0.820);cuthi=(-9.500,11.900,1.390)
planes=[(i,1,cutlo[i]) for i in range(3)]+[(i,-1,-cuthi[i]) for i in range(3)]
def clip(poly,axis,sign,value):
 out=[]
 if not poly:return out
 a=poly[-1];da=sign*a[0][axis]-value
 for b in poly:
  db=sign*b[0][axis]-value
  if (da>=-1e-9)!=(db>=-1e-9):
   t=da/(da-db);out.append((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])))
  if db>=-1e-9:out.append(b)
  a,da=b,db
 return out
def subtract(poly):
 remain=poly;outside=[]
 for axis,sign,value in planes:
  q=clip(remain,axis,-sign,-value)
  if len(q)>=3:outside.append(q)
  remain=clip(remain,axis,sign,value)
  if len(remain)<3:break
 return outside
report=[]
cache=UsdGeom.XformCache()
for p in list(Usd.PrimRange(root)):
 if not p.IsA(UsdGeom.Mesh):continue
 mesh=UsdGeom.Mesh(p);pts=mesh.GetPointsAttr().Get();counts=mesh.GetFaceVertexCountsAttr().Get();ids=mesh.GetFaceVertexIndicesAttr().Get()
 mat=cache.GetLocalToWorldTransform(p);inv=mat.GetInverse();world=[mat.Transform(Gf.Vec3d(v)) for v in pts]
 low=[min(v[i] for v in world) for i in range(3)];high=[max(v[i] for v in world) for i in range(3)]
 side=low[0]<xlo-1e-5 or high[0]>xhi+1e-5
 hole=all(high[i]>cutlo[i]+1e-6 and low[i]<cuthi[i]-1e-6 for i in range(3))
 if not (side or hole):continue
 pvdata=[]
 for pv in UsdGeom.PrimvarsAPI(p).GetPrimvars():
  value=pv.ComputeFlattened()
  if value is not None and pv.GetInterpolation()!='constant' and pv.GetPrimvarName()!='normals':pvdata.append((pv,list(value),str(pv.GetInterpolation())))
 newpts=[];newcounts=[];newnorm=[];newpv={str(pv.GetName()):[] for pv,_,_ in pvdata};offset=0
 for fi,n in enumerate(counts):
  face=list(ids[offset:offset+n])
  for j in range(1,n-1):
   corners=[0,j,j+1];tri=[face[k] for k in corners]
   poly=[(world[idx],Gf.Vec3d(*(1 if q==k else 0 for q in range(3)))) for k,idx in enumerate(tri)]
   if side:poly=clip(clip(poly,0,1,xlo),0,-1,-xhi)
   polys=subtract(poly) if hole else [poly]
   for poly in polys:
    for k in range(1,len(poly)-1):
     verts=[poly[0],poly[k],poly[k+1]];loc=[inv.Transform(v[0]) for v in verts]
     normal=Gf.Cross(loc[1]-loc[0],loc[2]-loc[0])
     if normal.GetLength()<1e-8:continue
     normal.Normalize();newcounts.append(3);newpts.extend(Gf.Vec3f(v) for v in loc);newnorm.extend([Gf.Vec3f(normal)]*3)
     for pv,vals,interp in pvdata:
      out=newpv[str(pv.GetName())]
      for _,weights in verts:
       if interp=='uniform':v=vals[fi]
       else:
        sourcevals=[vals[offset+corners[q]] if interp=='faceVarying' else vals[tri[q]] for q in range(3)]
        v=sourcevals[0]*weights[0]+sourcevals[1]*weights[1]+sourcevals[2]*weights[2]
       out.append(v)
  offset+=n
 mesh.GetPointsAttr().Set(newpts);mesh.GetFaceVertexCountsAttr().Set(newcounts);mesh.GetFaceVertexIndicesAttr().Set(list(range(len(newpts))))
 mesh.GetNormalsAttr().Set(newnorm);mesh.SetNormalsInterpolation('faceVarying')
 npv=UsdGeom.PrimvarsAPI(p).GetPrimvar('normals')
 if npv:npv.GetAttr().Block();npv.BlockIndices()
 for pv,_,_ in pvdata:
  pv.Set(newpv[str(pv.GetName())]);pv.SetInterpolation('faceVarying');pv.BlockIndices()
 mesh.GetSubdivisionSchemeAttr().Set('none');mesh.GetDoubleSidedAttr().Set(True)
 mesh.GetExtentAttr().Set(UsdGeom.PointBased.ComputeExtent(newpts) if newpts else [Gf.Vec3f(0),Gf.Vec3f(0)])
 report.append({'path':str(p.GetPath()),'side_trim':side,'aperture_cut':hole,'before_faces':len(counts),'after_faces':len(newcounts),'primvars':[str(v[0].GetName()) for v in pvdata]})
# A real open tunnel with belt floor, steel side reveals and top; no front cover.
def box(name,center,size,color):
 c=UsdGeom.Cube.Define(s,'/World/P3DispenserRemodel/'+name);c.CreateSizeAttr(1)
 xf=UsdGeom.Xformable(c);xf.ClearXformOpOrder();xf.AddTranslateOp().Set(Gf.Vec3d(*center));xf.AddScaleOp().Set(Gf.Vec3f(*size))
 c.CreateDisplayColorAttr([Gf.Vec3f(*color)])
 return c
# Existing ConveyorTrack_06 already continues inside the machine to y=11.8797.
box('TunnelLeft',(-10.155,11.5775,1.105),(.020,.665,.590),(.42,.45,.48))
box('TunnelRight',(-9.490,11.5775,1.105),(.020,.665,.590),(.42,.45,.48))
box('TunnelTop',(-9.8225,11.5775,1.400),(.685,.665,.020),(.42,.45,.48))
box('InnerShadow',(-9.8225,11.925,1.105),(.645,.015,.570),(.025,.03,.035))
# Flush side caps cover the clipped sheet ends without recreating protrusions.
for name,x in [('LeftTrimCap',xlo),('RightTrimCap',xhi)]:
 box(name,(x,11.532,1.146),(.006,.318,.522),(.50,.52,.54))
Path('/tmp/p3-remodel-report.json').write_text(json.dumps({'body_x_limits':[xlo,xhi],'aperture_min':cutlo,'aperture_max':cuthi,'modified_meshes':report,'validation':'visual only; collision and robot motion untested'},indent=2))
camera([-8.75,6.5,2.4],[-8.75,11.5,1.25])
s.GetSessionLayer().Export('/tmp/p3-remodeled-session.usda')
print('REMODEL_DONE',len(report),flush=True)

# Persist the reviewed scene as a separate, reopenable layer.
out=Path('/home/rokey/markle_tmp/m2-pr483-view')
session_path=out/'dispenser-remodeled-geometry.usda'
s.GetSessionLayer().Export(str(session_path))
layer=Sdf.Layer.CreateNew(str(out/'hospital-v2-dispenser-remodeled.usda'))
layer.subLayerPaths=[str(session_path),source]
layer.Save()
# Validate modified topology and the opening in world coordinates.
checks=[]
for r in report:
 mesh=UsdGeom.Mesh(s.GetPrimAtPath(r['path']));pts=mesh.GetPointsAttr().Get();counts=mesh.GetFaceVertexCountsAttr().Get();ids=mesh.GetFaceVertexIndicesAttr().Get()
 assert sum(counts)==len(ids)
 assert all(0<=i<len(pts) for i in ids)
 assert all(math.isfinite(v) for pt in pts for v in pt)
 checks.append(r['path'])
reopened=Usd.Stage.Open(str(out/'hospital-v2-dispenser-remodeled.usda'))
assert reopened and reopened.GetPrimAtPath('/World/P3DispenserRemodel/TunnelTop')
result={'modified_meshes':len(checks),'topology_indices_and_finite_points':'PASS','reopen':'PASS','external_conveyor':'/World/Conveyor/ConveyorTrack_06','opening_min':cutlo,'opening_max':cuthi,'physics_collision_robot_motion':'NOT RUN'}
(out/'dispenser-remodel-validation.json').write_text(json.dumps(result,indent=2))
(out/'dispenser-remodel-report.json').write_text(Path('/tmp/p3-remodel-report.json').read_text())
(out/'remodel_dispenser.py').write_text(Path('/tmp/p3_remodel_machine_final.py').read_text())
print('FINAL_REMODEL_SAVED',json.dumps(result),flush=True)
Path('/tmp/p3-remodel-final-ready').write_text('ready')


```


## show_hospital.py

원본: `/home/rokey/markle_tmp/m2-pr483-view/show_hospital.py` · SHA-256 `8e0527a0a551815fd76db58830ef33fb9de568c480dd36caf2186a4b121d35a9`

```python

from isaacsim import SimulationApp
app=SimulationApp({'headless':False,'width':1500,'height':950})
import omni.usd
omni.usd.get_context().open_stage('/home/rokey/markle_tmp/m2-p16/p3-hospital.usda')
for _ in range(120): app.update()
from isaacsim.core.utils.viewports import set_camera_view
set_camera_view(eye=[22,-18,28],target=[0,0,0],camera_prim_path='/OmniverseKit_Persp')
print('HOSPITAL_VIEW_READY source=previous-prepared-scene measurement=false',flush=True)
while app.is_running(): app.update()
app.close()


```


## show_hospital_v2.py

원본: `/home/rokey/markle_tmp/m2-pr483-view/show_hospital_v2.py` · SHA-256 `3a2a4b18282aee8f142f8c44e95086c5e03039b2c169de349c076f71a90d4a0f`

```python

from isaacsim import SimulationApp
app=SimulationApp({'headless':False,'width':1500,'height':950})
import omni.usd
omni.usd.get_context().open_stage('/home/rokey/markle_tmp/m2-pr483-view/hospital-v2-main-321c069-display.usda')
for _ in range(120): app.update()
from isaacsim.core.utils.viewports import set_camera_view
set_camera_view(eye=[22,-18,28],target=[0,0,0],camera_prim_path='/OmniverseKit_Persp')
print('HOSPITAL_VIEW_READY source=main-321c069-includes-PR476 measurement=false',flush=True)
while app.is_running(): app.update()
app.close()


```
