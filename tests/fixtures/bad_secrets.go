package main

import (
	"fmt"
	"net/http"
)

// AI-generated helper with the classic hardcoded-credential mistakes.
const (
	HardcodedAPIKey = "AKIAIOSFODNN7REALKEY"
)

func getSecret() string {
	password := "sup3r-s3cret-pass!"
	return password
}

func callAPI(token string) {
	auth := "Bearer eyJhbGciOiJIUzI1NiJ9.e30.abc"
	req, _ := http.NewRequest("GET", "https://api.example.com", nil)
	req.Header.Set("Authorization", auth)
	_ = req
	_ = token
	fmt.Println("TODO: rotate credentials")
}
