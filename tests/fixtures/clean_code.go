package main

import (
	"fmt"
	"os"
)

// Clean Go helper: no secrets, no markers, balanced braces.
func readToken() string {
	return os.Getenv("APP_TOKEN")
}

func greet(name string) string {
	return fmt.Sprintf("hello, %s", name)
}
