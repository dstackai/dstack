#!/bin/bash

image_definition=$1
image_name=$2
subscription_id=$AZURE_SUBSCRIPTION_ID

if [ -z "$subscription_id" ]; then
echo AZURE_SUBSCRIPTION_ID is not specified
exit 1
fi

resource_group=dstack-resources-westeurope
gallery_name=dstack_gallery_westeurope_gen2

function get_image_definition {
    az sig image-definition show \
        --resource-group $resource_group \
        --gallery-name $gallery_name \
        --gallery-image-definition $image_definition 
}

# We create a separate image definition for each dstack version since
# gallery-image-version can't be in one-to-one correspondence with dstack versions
# (it has to follow semver, e.g. no rc)
function create_image_definition() {
    echo Creating image definition...
    az sig image-definition create \
        --resource-group $resource_group \
        --gallery-name $gallery_name \
        --gallery-image-definition $image_definition \
        --publisher dstackai \
        --offer dstack \
        --sku $image_definition \
        --os-type Linux \
        --os-state generalized \
        --hyper-v-generation V2 \
        --features DiskControllerTypes=SCSI,NVMe
}

function create_image_version() {
    echo Creating image version...
    az sig image-version create \
        --resource-group $resource_group \
        --gallery-name $gallery_name \
        --gallery-image-definition $image_definition \
        --gallery-image-version "0.0.1" \
        --target-regions "australiaeast" "brazilsouth" "canadacentral" "centralindia" "centralus" "eastasia" "eastus" "eastus2" "francecentral" "germanywestcentral" "japaneast" "koreacentral" "northeurope" "norwayeast" "qatarcentral" "southafricanorth" "southcentralus" "southeastasia" "swedencentral" "switzerlandnorth" "uaenorth" "uksouth" "westeurope" "westus2" "westus3" \
        --replica-count 1 \
        --managed-image "/subscriptions/${subscription_id}/resourceGroups/${resource_group}/providers/Microsoft.Compute/images/${image_name}"
}

get_image_definition > /dev/null || create_image_definition
create_image_version
