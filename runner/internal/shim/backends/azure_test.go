package backends

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestGetsAzureMetadata(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(
			`{"compute":
				{
					"subscriptionId":"test_subscription",
					"resourceGroupName":"test_group",
					"name":"test_vm"
				}
			}`,
		))
	}))
	defer server.Close()
	metadata, err := getAzureMetadata(context.TODO(), &server.URL)
	assert.Equal(t, nil, err)
	assert.Equal(t, AzureComputeInstanceMetadata{
		SubscriptionId:    "test_subscription",
		ResourceGroupName: "test_group",
		Name:              "test_vm",
	}, *metadata)
}
