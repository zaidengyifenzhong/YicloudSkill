// Generate independent vectors by executing the unmodified pinned SDK implementation.
// Run: cd SDK_CHECKOUT && go run /path/to/YicloudSkill/tools/sign_vectors.go
package main

import (
	"encoding/json"
	"os"

	"gitee.com/yicloud-team/openapi-sdk-go/base/auth"
)

func main() {
	vectors := []map[string]string{
		{"timestamp": "1700000000123", "public": "fixture-public", "secret": "fixture-secret", "query": "z=&a=%E4%B8%AD%E6%96%87&a=two+words&bare&false=false&zero=0", "body": "{\"Image\":\"测试\",\"Enabled\":false}"},
		{"timestamp": "0", "public": "p", "secret": "s", "query": "", "body": ""},
		{"timestamp": "1792396800000", "public": "public", "secret": "secret", "query": "A=1&A=2&a=3&escaped=%26%3D&plus=%2B", "body": "{\"n\":0,\"empty\":\"\",\"nil\":null}"},
	}
	for _, v := range vectors {
		s, e := auth.HmacSign(v["timestamp"], v["public"], v["secret"], v["query"], v["body"])
		if e != nil {
			panic(e)
		}
		v["signature"] = s
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(vectors); err != nil {
		panic(err)
	}
}
