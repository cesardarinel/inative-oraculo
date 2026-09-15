// Proxy TLS plano<->TLS capturando ambos sentidos descifrados, para capturar
// el data stream 5250 real de PUB400 usando tn5250j como terminal.
// Uso: go run proxytls.go <listenAddr> <targetAddr> <logfile>
package main

import (
	"crypto/tls"
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"strings"
	"sync"
	"time"
)

func main() {
	listen := "127.0.0.1:9992"
	target := "pub400.com:992"
	logFile := "proxytls.log"
	if len(os.Args) > 1 {
		listen = os.Args[1]
	}
	if len(os.Args) > 2 {
		target = os.Args[2]
	}
	if len(os.Args) > 3 {
		logFile = os.Args[3]
	}

	ln, err := net.Listen("tcp", listen)
	if err != nil {
		log.Fatalf("listen %s: %v", listen, err)
	}
	log.Printf("proxy %s -> TLS %s, log=%s", listen, target, logFile)

	for {
		cli, err := ln.Accept()
		if err != nil {
			log.Fatal(err)
		}
		go handle(cli, target, logFile)
	}
}

func handle(cli net.Conn, target, logFile string) {
	defer cli.Close()
	tlsCfg := &tls.Config{InsecureSkipVerify: true}
	up, err := tls.Dial("tcp", target, tlsCfg)
	if err != nil {
		log.Printf("dial %s: %v", target, err)
		return
	}
	defer up.Close()
	log.Printf("conexión: %s <-> %s", cli.RemoteAddr(), target)

	var mu sync.Mutex
	var wg sync.WaitGroup
	wg.Add(2)

	// registro de eventos con timestamps + hex + ascii
	reg := func(dir string, data []byte) {
		if len(data) == 0 {
			return
		}
		mu.Lock()
		defer mu.Unlock()
		f, err := os.OpenFile(logFile, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
		if err != nil {
			return
		}
		defer f.Close()
		t := time.Now().Format("15:04:05.000")
		var ascii strings.Builder
		for _, b := range data {
			if b >= 32 && b <= 126 {
				ascii.WriteByte(b)
			} else {
				ascii.WriteByte('.')
			}
		}
		fmt.Fprintf(f, "=== %s [%s] %d bytes ===\n%s\nascii: %s\n\n", t, dir, len(data), hexStr(data), ascii.String())
	}

	copy := func(dst net.Conn, src net.Conn, dir string) {
		defer wg.Done()
		buf := make([]byte, 8192)
		for {
			n, err := src.Read(buf)
			if n > 0 {
				reg(dir, buf[:n])
				if _, werr := dst.Write(buf[:n]); werr != nil {
					return
				}
			}
			if err != nil {
				return
			}
		}
	}
	go copy(up, cli, "C->up")
	go copy(cli, up, "up->C")
	wg.Wait()
}

func hexStr(b []byte) string {
	const per = 16
	var sb strings.Builder
	for i := 0; i < len(b); i += per {
		end := i + per
		if end > len(b) {
			end = len(b)
		}
		for j := i; j < end; j++ {
			sb.WriteString(fmt.Sprintf("%02x ", b[j]))
		}
		sb.WriteString("\n")
	}
	return sb.String()
}

var _ = io.Copy