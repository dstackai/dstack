from dstack._internal.core.models.compute_groups import ComputeGroup, ComputeGroupProvisioningData
from dstack._internal.server.models import ComputeGroupModel


def compute_group_model_to_compute_group(compute_group_model: ComputeGroupModel) -> ComputeGroup:
    provisioning_data = get_compute_group_provisioning_data(compute_group_model)
    return ComputeGroup(
        id=compute_group_model.id,
        project_name=compute_group_model.project.name,
        status=compute_group_model.status,
        name=provisioning_data.compute_group_name,
        created_at=compute_group_model.created_at,
        provisioning_data=provisioning_data,
    )


def get_compute_group_provisioning_data(
    compute_group_model: ComputeGroupModel,
) -> ComputeGroupProvisioningData:
    return ComputeGroupProvisioningData.__response__.parse_raw(
        compute_group_model.provisioning_data
    )
