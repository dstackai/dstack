#/bin/bash

image_definition=$1
image_version=$2
image_name=$3
subscription_id=$AZURE_SUBSCRIPTION_ID

if [ -z "$subscription_id" ]; then
echo AZURE_SUBSCRIPTION_ID is not specified
exit 1
fi

resource_group=dstack-resources-germanywestcentral
gallery_name=dstack_gallery_germanywestcentral

function get_image_definition {
    az sig image-definition show \
        --resource-group $resource_group \
        --gallery-name $gallery_name \
        --gallery-image-definition $image_definition 
}

function create_image_definition() {
    echo Creating image definition...
    az sig image-definition create \
        --resource-group $resource_group \
        --gallery-name $gallery_name \
        --gallery-image-definition $image_definition \
        --publisher dstackai \
        --offer dstack-1 \
        --sku $image_definition \
        --os-type Linux \
        --os-state generalized
}

function create_image_version() {
    echo Creating image version...
    az sig image-version create \
        --resource-group $resource_group \
        --gallery-name $gallery_name \
        --gallery-image-definition $image_definition \
        --gallery-image-version $image_version \
        --target-regions "australiacentral" "australiacentral2" "australiaeast" "australiasoutheast" "brazilsouth" "brazilsoutheast" "canadacentral" "canadaeast" "centralindia" "centralus" "centraluseuap" "eastasia" "eastus" "eastus2" "eastus2euap" "eastusstg" "francecentral" "francesouth" "germanynorth" "germanywestcentral" "japaneast" "japanwest" "jioindiacentral" "jioindiawest" "koreacentral" "koreasouth" "northcentralus" "northeurope" "norwayeast" "norwaywest" "qatarcentral" "southafricanorth" "southafricawest" "southcentralus" "southeastasia" "southindia" "swedencentral" "switzerlandnorth" "switzerlandwest" "uaecentral" "uaenorth" "uksouth" "ukwest" "westcentralus" "westeurope" "westindia" "westus" "westus2" "westus3" \
        --replica-count 1 \
        --managed-image "/subscriptions/${subscription_id}/resourceGroups/packer/providers/Microsoft.Compute/images/${image_name}"
}

get_image_definition > /dev/null || create_image_definition
create_image_version
