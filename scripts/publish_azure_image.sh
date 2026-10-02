#!/bin/bash

set -o pipefail

image_definition=$1
image_name=$2
# If true, publish a new gallery version when the image definition already has versions
new_gallery_version=${3:-false}
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

function get_latest_image_version() {
    az sig image-version list \
        --resource-group $resource_group \
        --gallery-name $gallery_name \
        --gallery-image-definition $image_definition \
        --query "[].name" \
        --output tsv |
        sort -V |
        tail -1
}

function create_image_version() {
    echo Creating image version $1...
    az sig image-version create \
        --resource-group $resource_group \
        --gallery-name $gallery_name \
        --gallery-image-definition $image_definition \
        --gallery-image-version "$1" \
        --target-regions "australiaeast" "brazilsouth" "canadacentral" "centralindia" "centralus" "eastasia" "eastus" "eastus2" "francecentral" "germanywestcentral" "japaneast" "koreacentral" "northeurope" "norwayeast" "qatarcentral" "southafricanorth" "southcentralus" "southeastasia" "swedencentral" "switzerlandnorth" "uaenorth" "uksouth" "westeurope" "westus2" "westus3" \
        --replica-count 1 \
        --managed-image "/subscriptions/${subscription_id}/resourceGroups/${resource_group}/providers/Microsoft.Compute/images/${image_name}"
}

get_image_definition > /dev/null || create_image_definition

latest_version=$(get_latest_image_version) || exit 1
if [ -z "$latest_version" ]; then
    image_version=0.0.1
elif [ "$new_gallery_version" = true ]; then
    image_version="${latest_version%.*}.$((${latest_version##*.} + 1))"
else
    echo "$image_definition already has gallery version $latest_version." \
        "Enable azure_new_gallery_version to publish a new one."
    exit 1
fi
create_image_version $image_version
