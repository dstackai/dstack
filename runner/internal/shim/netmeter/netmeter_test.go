package netmeter

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParseByteCounter(t *testing.T) {
	tests := []struct {
		name      string
		output    string
		expected  int64
		expectErr bool
	}{
		{
			name: "typical output with traffic",
			output: `Chain dstack-nm (1 references)
    pkts      bytes target     prot opt in     out     source               destination
       0        0 RETURN     all  --  *      *       0.0.0.0/0            10.0.0.0/8
       0        0 RETURN     all  --  *      *       0.0.0.0/0            172.16.0.0/12
       0        0 RETURN     all  --  *      *       0.0.0.0/0            192.168.0.0/16
       0        0 RETURN     all  --  *      *       0.0.0.0/0            169.254.0.0/16
       0        0 RETURN     all  --  *      *       0.0.0.0/0            127.0.0.0/8
     123   456789 RETURN     all  --  *      *       0.0.0.0/0            0.0.0.0/0
`,
			expected: 456789,
		},
		{
			name: "zero traffic",
			output: `Chain dstack-nm (1 references)
    pkts      bytes target     prot opt in     out     source               destination
       0        0 RETURN     all  --  *      *       0.0.0.0/0            10.0.0.0/8
       0        0 RETURN     all  --  *      *       0.0.0.0/0            172.16.0.0/12
       0        0 RETURN     all  --  *      *       0.0.0.0/0            192.168.0.0/16
       0        0 RETURN     all  --  *      *       0.0.0.0/0            169.254.0.0/16
       0        0 RETURN     all  --  *      *       0.0.0.0/0            127.0.0.0/8
       0        0 RETURN     all  --  *      *       0.0.0.0/0            0.0.0.0/0
`,
			expected: 0,
		},
		{
			name: "large byte count",
			output: `Chain dstack-nm (1 references)
    pkts      bytes target     prot opt in     out     source               destination
   10000  5000000 RETURN     all  --  *      *       0.0.0.0/0            10.0.0.0/8
       0        0 RETURN     all  --  *      *       0.0.0.0/0            172.16.0.0/12
       0        0 RETURN     all  --  *      *       0.0.0.0/0            192.168.0.0/16
       0        0 RETURN     all  --  *      *       0.0.0.0/0            169.254.0.0/16
       0        0 RETURN     all  --  *      *       0.0.0.0/0            127.0.0.0/8
  500000 107374182400 RETURN     all  --  *      *       0.0.0.0/0            0.0.0.0/0
`,
			expected: 107374182400, // ~100 GB
		},
		{
			name:      "empty output",
			output:    "",
			expectErr: true,
		},
		{
			name: "only headers no rules",
			output: `Chain dstack-nm (1 references)
    pkts      bytes target     prot opt in     out     source               destination
`,
			expectErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := parseByteCounter(tt.output)
			if tt.expectErr {
				assert.Error(t, err)
			} else {
				require.NoError(t, err)
				assert.Equal(t, tt.expected, result)
			}
		})
	}
}

func TestNew(t *testing.T) {
	nm := New()
	assert.NotNil(t, nm)
	assert.Equal(t, int64(0), nm.Bytes())
}
