package safeexec

import "testing"

func TestValidateWhoami(t *testing.T) {
	argv, err := Validate("whoami")
	if err != nil || len(argv) != 1 {
		t.Fatalf("%v %v", argv, err)
	}
}

func TestRejectSemicolon(t *testing.T) {
	_, err := Validate("whoami; rm -rf /")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestRejectRm(t *testing.T) {
	_, err := Validate("rm -rf /tmp")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestPingImplicitCount(t *testing.T) {
	argv, err := Validate("ping 127.0.0.1")
	if err != nil {
		t.Fatal(err)
	}
	if len(argv) != 4 || argv[0] != "ping" || argv[1] != "-c" || argv[2] != "3" {
		t.Fatalf("%v", argv)
	}
}

func TestCurlURL(t *testing.T) {
	argv, err := Validate("curl https://example.com/")
	if err != nil || len(argv) != 2 {
		t.Fatalf("%v %v", argv, err)
	}
}
