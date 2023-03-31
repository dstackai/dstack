package local

import (
	"context"
	"fmt"
	"testing"
)

func TestIsInterruptedSpot(t *testing.T) {
	ctx := context.TODO()
	client := NewClientEC2("eu-west-1")
	res, _ := client.IsInterruptedSpot(ctx, "sir-8566hnkj")
	fmt.Printf("Res: %t\n", res)
}
