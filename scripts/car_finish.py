"""Controlled materials on the existing licensed generic concept car."""


def refine_finish(body,carbon,accent,tire,rim):
    for mat,values in ((body,{'Metallic':.22,'Roughness':.32,'Coat Weight':.28,'Coat Roughness':.18}),
                       (accent,{'Metallic':.16,'Roughness':.33,'Coat Weight':.22}),
                       (carbon,{'Metallic':.05,'Roughness':.43,'Coat Weight':.10}),
                       (tire,{'Metallic':0.,'Roughness':.76,'Coat Weight':0.}),
                       (rim,{'Metallic':.82,'Roughness':.28})):
        shader=mat.node_tree.nodes.get('Principled BSDF')
        for key,value in values.items():
            if key in shader.inputs:shader.inputs[key].default_value=value
