package api

type RegistryAuthBody struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type HealthcheckResponse struct {
	Service string `json:"service"`
}

type PullResponse struct {
	State string `json:"state"`
}
