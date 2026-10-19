// Extract actual request operations and Go request schemas using only the standard library.
package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"sort"
	"strconv"
	"strings"
)

type M = map[string]any

func fail(f string, a ...any) { panic(fmt.Sprintf(f, a...)) }
func lit(e ast.Expr) string {
	if v, ok := e.(*ast.BasicLit); ok {
		s, err := strconv.Unquote(v.Value)
		if err == nil {
			return s
		}
	}
	fail("unresolved literal %T", e)
	return ""
}
func schema(e ast.Expr) M {
	switch t := e.(type) {
	case *ast.StarExpr:
		s := schema(t.X)
		s["nullable"] = true
		return s
	case *ast.Ident:
		switch t.Name {
		case "string":
			return M{"type": "string"}
		case "bool":
			return M{"type": "boolean"}
		case "any", "interface{}":
			return M{}
		case "float32", "float64":
			return M{"type": "number"}
		case "int", "int8", "int16", "int32", "int64", "uint", "uint8", "uint16", "uint32", "uint64":
			return M{"type": "integer"}
		}
		return M{"ref": t.Name}
	case *ast.ArrayType:
		return M{"type": "array", "items": schema(t.Elt)}
	case *ast.MapType:
		if k, ok := t.Key.(*ast.Ident); !ok || k.Name != "string" {
			fail("non-string map key")
		}
		return M{"type": "object", "additional": schema(t.Value)}
	case *ast.InterfaceType:
		return M{}
	case *ast.SelectorExpr:
		if t.Sel.Name == "Time" {
			return M{"type": "string", "format": "date-time"}
		}
		fail("unresolved selector %s", t.Sel.Name)
	case *ast.StructType:
		props := M{}
		required := []string{}
		for _, f := range t.Fields.List {
			if len(f.Names) == 0 {
				fail("embedded schema field")
			}
			tag := reflect.StructTag("")
			if f.Tag != nil {
				tag = reflect.StructTag(lit(f.Tag))
			}
			name := strings.Split(tag.Get("json"), ",")[0]
			if name == "-" {
				continue
			}
			if name == "" {
				name = f.Names[0].Name
			}
			s := schema(f.Type)
			s["description"] = strings.TrimSpace(f.Doc.Text() + f.Comment.Text())
			s["binding"] = tag.Get("binding")
			if form := tag.Get("form"); form != "" {
				s["query_name"] = strings.Split(form, ",")[0]
			}
			for _, b := range strings.Split(tag.Get("binding"), ",") {
				if b == "required" {
					required = append(required, name)
				}
				if strings.HasPrefix(b, "oneof=") {
					s["enum"] = strings.Fields(strings.TrimPrefix(b, "oneof="))
				}
			}
			props[name] = s
		}
		return M{"type": "object", "properties": props, "required": required}
	}
	fail("unresolved schema %T", e)
	return nil
}
func main() {
	if len(os.Args) != 2 {
		fail("usage: go run tools/catalog.go SDK_ROOT")
	}
	root := os.Args[1]
	pinned := "8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5"
	head, err := exec.Command("git", "-C", root, "rev-parse", "HEAD").Output()
	if err != nil || strings.TrimSpace(string(head)) != pinned {
		fail("SDK checkout must be pinned to %s", pinned)
	}
	dirty, err := exec.Command("git", "-C", root, "status", "--porcelain", "--untracked-files=no").Output()
	if err != nil || len(dirty) != 0 {
		fail("SDK source has tracked modifications")
	}
	ops := []M{}
	defs := M{}
	err = filepath.WalkDir(filepath.Join(root, "services"), func(p string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.Name() != "actions.go" {
			return nil
		}
		dir := filepath.Dir(p)
		rel, _ := filepath.Rel(root, dir)
		key := strings.TrimPrefix(filepath.ToSlash(rel), "services/")
		fs := token.NewFileSet()
		files, e := parser.ParseDir(fs, dir, func(i os.FileInfo) bool { return !strings.HasSuffix(i.Name(), "_test.go") }, parser.ParseComments)
		if e != nil {
			return e
		}
		var product, version string
		local := M{}
		constants := map[string]string{}
		var acts *ast.File
		for _, pkg := range files {
			for path, f := range pkg.Files {
				if filepath.Base(path) == "actions.go" {
					acts = f
				}
				ast.Inspect(f, func(n ast.Node) bool {
					if kv, ok := n.(*ast.KeyValueExpr); ok {
						if id, ok := kv.Key.(*ast.Ident); ok {
							switch id.Name {
							case "productCode":
								product = lit(kv.Value)
							case "lastVersion":
								version = lit(kv.Value)
							}
						}
					}
					return true
				})
				if filepath.Base(path) == "models.go" || filepath.Base(path) == "actions.go" {
					for _, decl := range f.Decls {
						if g, ok := decl.(*ast.GenDecl); ok && g.Tok == token.CONST {
							for _, spec := range g.Specs {
								v := spec.(*ast.ValueSpec)
								for i, n := range v.Names {
									if i < len(v.Values) {
										if b, ok := v.Values[i].(*ast.BasicLit); ok && b.Kind == token.STRING {
											constants[n.Name] = lit(b)
										}
									}
								}
							}
						}
						if g, ok := decl.(*ast.GenDecl); ok && g.Tok == token.TYPE {
							for _, spec := range g.Specs {
								t := spec.(*ast.TypeSpec)
								if t.Name.IsExported() {
									local[t.Name.Name] = schema(t.Type)
								}
							}
						}
					}
				}
			}
		}
		if product == "" || version == "" {
			fail("missing service metadata %s", key)
		}
		var check func(M)
		check = func(s M) {
			if ref, ok := s["ref"].(string); ok {
				if _, exists := local[ref]; !exists {
					fail("unresolved type %s/%s", key, ref)
				}
			}
			if desc, ok := s["description"].(string); ok && strings.Contains(desc, "SDK常量:") {
				values := []string{}
				for _, name := range strings.Split(strings.SplitN(desc, "SDK常量:", 2)[1], ",") {
					v, ok := constants[strings.TrimSpace(name)]
					if !ok {
						fail("unknown enum %s", name)
					}
					values = append(values, v)
				}
				s["enum"] = values
			}
			for _, v := range s {
				if m, ok := v.(M); ok {
					check(m)
				}
			}
		}
		for _, v := range local {
			check(v.(M))
		}
		defs[key] = local
		for _, decl := range acts.Decls {
			f, ok := decl.(*ast.FuncDecl)
			if !ok || !f.Name.IsExported() || f.Recv != nil {
				continue
			}
			var method, pathAction, request string
			mode := "envelope"
			calls := 0
			ast.Inspect(f.Body, func(n ast.Node) bool {
				if c, ok := n.(*ast.CallExpr); ok {
					if sel, ok := c.Fun.(*ast.SelectorExpr); ok {
						if id, ok := sel.X.(*ast.Ident); ok && id.Name == "client" && (sel.Sel.Name == "Get" || sel.Sel.Name == "Post" || sel.Sel.Name == "GetRaw") {
							calls++
							method = strings.ToUpper(sel.Sel.Name)
							if method == "GETRAW" {
								method = "GET"
								mode = "file"
							}
						}
						if id, ok := sel.X.(*ast.Ident); ok && id.Name == "fmt" && sel.Sel.Name == "Sprintf" && len(c.Args) == 4 && lit(c.Args[0]) == "/%s/%s/%s" {
							switch a := c.Args[3].(type) {
							case *ast.BasicLit:
								pathAction = lit(a)
							case *ast.CallExpr:
								if s, ok := a.Fun.(*ast.SelectorExpr); ok && s.Sel.Name == "GetCurrentFuncsName" {
									pathAction = f.Name.Name
								} else {
									fail("unresolved path %s", f.Name.Name)
								}
							default:
								fail("unresolved path %s", f.Name.Name)
							}
						}
					}
				}
				return true
			})
			if calls == 0 {
				fail("exported operation has no recognized request: %s/%s", key, f.Name.Name)
			}
			if calls != 1 || pathAction == "" {
				fail("ambiguous operation %s/%s", key, f.Name.Name)
			}
			for _, p := range f.Type.Params.List {
				for _, n := range p.Names {
					if n.Name == "req" {
						t, ok := p.Type.(*ast.StarExpr)
						if !ok {
							fail("request not pointer")
						}
						request = t.X.(*ast.Ident).Name
					}
				}
			}
			if request == "" {
				fail("missing request %s", f.Name.Name)
			}
			if _, ok := local[request]; !ok {
				fail("unresolved request %s", request)
			}
			if key == "fs/alpha" {
				mode = "direct"
				if strings.HasPrefix(f.Name.Name, "Delete") {
					mode = "empty"
				}
			}
			if f.Name.Name == "GetRayJobLogs" {
				mode = "direct"
			}
			if f.Name.Name == "DownloadInferSetLogs" {
				mode = "file"
			}
			status := "implemented-offline"
			if f.Name.Name == "GetInferSetTerminal" || f.Name.Name == "GetInferSetLogsTail" {
				mode = "deferred"
				status = "deferred-protocol"
			}
			ops = append(ops, M{"service": key, "product": product, "version": version, "action": f.Name.Name, "method": method, "path": "/" + product + "/" + version + "/" + pathAction, "request": request, "read_only": method == "GET" && !strings.HasPrefix(f.Name.Name, "Release") || key == "fs/alpha" && strings.HasPrefix(f.Name.Name, "List"), "response_mode": mode, "status": status, "description": strings.TrimSpace(f.Doc.Text()), "source": filepath.ToSlash(rel) + "/actions.go", "line": fs.Position(f.Pos()).Line})
		}
		return nil
	})
	if err != nil {
		panic(err)
	}
	sort.Slice(ops, func(i, j int) bool {
		return fmt.Sprint(ops[i]["service"], ops[i]["action"]) < fmt.Sprint(ops[j]["service"], ops[j]["action"])
	})
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(M{"sdk_version": "v0.5.1", "sdk_commit": "8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5", "checked": "2026-10-19", "operations": ops, "definitions": defs}); err != nil {
		panic(err)
	}
}
