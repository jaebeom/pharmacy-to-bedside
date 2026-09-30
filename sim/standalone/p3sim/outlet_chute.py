"""Opt-in passive outlet chute derived from measured roller and receiving-table bounds."""
import math


def chute_geometry(source, receiver, direction, *, entry_overlap, landing_overlap,
                   width_margin, thickness, entry_recess=0.):
    if direction not in ('+x', '-x', '+y', '-y'):
        raise ValueError('chute direction must be horizontal and axis-aligned')
    if not all(math.isfinite(v) and v > 0 for v in
               (entry_overlap, landing_overlap, width_margin, thickness)):
        raise ValueError('chute dimensions must be positive and finite')
    if not math.isfinite(entry_recess) or not 0 <= entry_recess < thickness:
        raise ValueError('entry recess must be nonnegative and less than plate thickness')
    axis = 0 if direction[1] == 'x' else 1
    cross = 1-axis
    sign = 1 if direction[0] == '+' else -1
    lo = max(source['min'][cross], receiver['min'][cross])+width_margin
    hi = min(source['max'][cross], receiver['max'][cross])-width_margin
    if hi-lo < .1:
        raise ValueError('roller and receiver have insufficient shared width')
    exit_edge = source['max' if sign > 0 else 'min'][axis]
    table_entry = receiver['min' if sign > 0 else 'max'][axis]
    start = [0., 0., source['max'][2]-entry_recess]
    end = [0., 0., receiver['max'][2]]
    start[cross] = end[cross] = (lo+hi)/2
    start[axis] = exit_edge-sign*entry_overlap
    end[axis] = table_entry+sign*landing_overlap
    run = sign*(end[axis]-start[axis])
    drop = start[2]-end[2]
    if run <= 0 or drop <= 0 or not receiver['min'][axis] < end[axis] < receiver['max'][axis]:
        raise ValueError('chute must descend forward onto the receiving surface')
    if entry_overlap >= source['max'][axis]-source['min'][axis]:
        raise ValueError('chute entry overlap exceeds source surface')
    travel = [0., 0., 0.]
    travel[axis] = sign
    lateral = (travel[1], -travel[0], 0.)
    top = [[p[i]+side*lateral[i]*(hi-lo)/2 for i in range(3)]
           for p, side in ((start, -1), (start, 1), (end, 1), (end, -1))]
    points = top+[[p[0], p[1], p[2]-thickness] for p in top]
    return {'points': points, 'start': start, 'end': end, 'width': hi-lo,
            'run': run, 'drop': drop, 'entry_recess': entry_recess,
            'slope_degrees': math.degrees(math.atan2(drop, run))}


def build_chute(stage, source, config, direction):
    from pxr import Gf, Usd, UsdGeom, UsdPhysics, UsdShade
    receiver = stage.GetPrimAtPath(config['receiver_prim'])
    if not receiver:
        raise ValueError('missing measured receiving table')
    bound = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render,
                                                     UsdGeom.Tokens.proxy]).ComputeWorldBound(receiver)
    aligned = bound.ComputeAlignedRange()
    surface = {'min': list(aligned.GetMin()), 'max': list(aligned.GetMax())}
    if not all(math.isfinite(v) for v in surface['min']+surface['max']):
        raise ValueError('receiving surface has invalid bounds')
    geometry = chute_geometry(source, surface, direction, entry_overlap=config['entry_overlap_m'],
                              landing_overlap=config['landing_overlap_m'], width_margin=config['width_margin_m'],
                              thickness=config['thickness_m'], entry_recess=config.get('entry_recess_m', 0.))
    static, dynamic = config['static_friction'], config['dynamic_friction']
    if not 0 <= dynamic <= static <= 1:
        raise ValueError('chute friction must satisfy 0 <= dynamic <= static <= 1')
    root = '/World/ConveyorProbe/OutletChute'
    mesh = UsdGeom.Mesh.Define(stage, root)
    mesh.CreatePointsAttr([Gf.Vec3f(*point) for point in geometry['points']])
    mesh.CreateFaceVertexCountsAttr([4]*6)
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3, 7, 6, 5, 4, 0, 4, 5, 1,
                                    1, 5, 6, 2, 2, 6, 7, 3, 3, 7, 4, 0])
    mesh.CreateSubdivisionSchemeAttr('none')
    mesh.CreateDisplayColorAttr([Gf.Vec3f(.58, .63, .68)])
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim()).CreateCollisionEnabledAttr(True)
    UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr('convexHull')
    material = UsdShade.Material.Define(stage, '/World/ConveyorProbe/ChuteMaterial')
    physics = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
    physics.CreateStaticFrictionAttr(static)
    physics.CreateDynamicFrictionAttr(dynamic)
    physics.CreateRestitutionAttr(0.)
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(
        material, bindingStrength=UsdShade.Tokens.weakerThanDescendants, materialPurpose='physics')
    # The original table mesh stays in place. This is a passive plate, not a moving belt or teleport.
    return surface, dict(geometry, prim=root, receiver_prim=str(receiver.GetPath()),
                         static_friction=static, dynamic_friction=dynamic)
