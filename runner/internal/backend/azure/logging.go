package azure

import (
	"os"
)

type AzureLogging struct {
}

func NewAzureLogging() *AzureLogging {
	return &AzureLogging{}
}

func (azlogging AzureLogging) Write(p []byte) (n int, err error) {
	return os.Stderr.Write(p)
}
