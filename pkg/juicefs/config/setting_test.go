/*
Copyright 2021 Juicedata Inc

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package config

import (
	"encoding/json"
	"fmt"
	"reflect"
	"testing"
)

func TestParseSecret(t *testing.T) {
	s := map[string]string{"GOOGLE_APPLICATION_CREDENTIALS": "/root/.config/gcloud/application_default_credentials.json"}
	ss, _ := json.Marshal(s)
	fmt.Println(string(ss))

	type args struct {
		secrets map[string]string
		volCtx  map[string]string
		usePod  bool
	}
	tests := []struct {
		name    string
		args    args
		want    *JfsSetting
		wantErr bool
	}{
		{
			name: "test",
			args: args{
				secrets: map[string]string{
					"name": "test",
					"envs": "GOOGLE_APPLICATION_CREDENTIALS: \"/root/.config/gcloud/application_default_credentials.json\"",
				},
				usePod: true,
			},
			want: &JfsSetting{
				Name:   "test",
				Envs:   s,
				UsePod: true,
			},
			wantErr: false,
		},
		{
			name: "test-storage-nil",
			args: args{
				secrets: map[string]string{
					"name": "test",
				},
				usePod: true,
			},
			want: &JfsSetting{
				Name:    "test",
				Storage: "",
				UsePod:  true,
			},
			wantErr: false,
		},
		{
			name: "test-storage",
			args: args{
				secrets: map[string]string{
					"name":    "test",
					"storage": "ceph",
				},
				usePod: true,
			},
			want: &JfsSetting{
				Name:    "test",
				Storage: "ceph",
				UsePod:  true,
			},
			wantErr: false,
		},
		{
			name: "test-cpu-limit",
			args: args{
				secrets: map[string]string{
					"name":    "test",
					"storage": "s3",
				},
				volCtx: map[string]string{
					mountPodCpuLimitKey: "1",
				},
				usePod: true,
			},
			want: &JfsSetting{
				Name:             "test",
				Storage:          "s3",
				UsePod:           true,
				MountPodCpuLimit: "1",
			},
			wantErr: false,
		},
		{
			name: "test-mem-limit",
			args: args{
				secrets: map[string]string{
					"name":    "test",
					"storage": "s3",
				},
				volCtx: map[string]string{
					mountPodMemLimitKey: "1G",
				},
				usePod: true,
			},
			want: &JfsSetting{
				Name:             "test",
				Storage:          "s3",
				UsePod:           true,
				MountPodMemLimit: "1G",
			},
			wantErr: false,
		},
		{
			name: "test-mem-request",
			args: args{
				secrets: map[string]string{
					"name":    "test",
					"storage": "s3",
				},
				volCtx: map[string]string{
					mountPodMemRequestKey: "1G",
				},
				usePod: true,
			},
			want: &JfsSetting{
				Name:               "test",
				Storage:            "s3",
				UsePod:             true,
				MountPodMemRequest: "1G",
			},
			wantErr: false,
		},
		{
			name: "test-cpu-request",
			args: args{
				secrets: map[string]string{
					"name":    "test",
					"storage": "s3",
				},
				volCtx: map[string]string{
					mountPodCpuRequestKey: "1",
				},
				usePod: true,
			},
			want: &JfsSetting{
				Name:               "test",
				Storage:            "s3",
				UsePod:             true,
				MountPodCpuRequest: "1",
			},
			wantErr: false,
		},
		{
			name: "test-labels",
			args: args{
				secrets: map[string]string{
					"name":    "test",
					"storage": "s3",
				},
				volCtx: map[string]string{
					"juicefs/mount-labels": "a: b",
				},
				usePod: true,
			},
			want: &JfsSetting{
				Name:           "test",
				Storage:        "s3",
				MountPodLabels: map[string]string{"a": "b"},
				UsePod:         true,
			},
			wantErr: false,
		},
		{
			name: "test-labels-json",
			args: args{
				secrets: map[string]string{
					"name":    "test",
					"storage": "s3",
				},
				volCtx: map[string]string{
					"juicefs/mount-labels": "{\"a\": \"b\"}",
				},
				usePod: true,
			},
			want: &JfsSetting{
				Name:           "test",
				Storage:        "s3",
				MountPodLabels: map[string]string{"a": "b"},
				UsePod:         true,
			},
			wantErr: false,
		},
		{
			name: "test-annotation",
			args: args{
				secrets: map[string]string{
					"name":    "test",
					"storage": "s3",
				},
				volCtx: map[string]string{
					"juicefs/mount-annotations": "a: b",
				},
				usePod: true,
			},
			want: &JfsSetting{
				Name:                "test",
				Storage:             "s3",
				MountPodAnnotations: map[string]string{"a": "b"},
				UsePod:              true,
			},
			wantErr: false,
		},
		{
			name: "test-serviceaccount",
			args: args{
				secrets: map[string]string{
					"name":    "test",
					"storage": "s3",
				},
				volCtx: map[string]string{
					"juicefs/mount-service-account": "test",
				},
				usePod: true,
			},
			want: &JfsSetting{
				UsePod:                 true,
				Name:                   "test",
				Storage:                "s3",
				MountPodServiceAccount: "test",
			},
			wantErr: false,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseSetting(tt.args.secrets, tt.args.volCtx, tt.args.usePod)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseSecret() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("ParseSecret() got = %v, want %v", got, tt.want)
			}
		})
	}
}

func Test_parseYamlOrJson(t *testing.T) {
	jsonDst := make(map[string]string)
	yamlDst := make(map[string]string)
	type args struct {
		source string
		dst    interface{}
	}
	tests := []struct {
		name    string
		args    args
		wantErr bool
		wantDst interface{}
	}{
		{
			name: "test-json",
			args: args{
				source: "{\"a\": \"b\", \"c\": \"d\"}",
				dst:    &jsonDst,
			},
			wantErr: false,
			wantDst: map[string]string{
				"a": "b",
				"c": "d",
			},
		},
		{
			name: "test-yaml",
			args: args{
				source: "c: d\ne: f",
				dst:    &yamlDst,
			},
			wantErr: false,
			wantDst: map[string]string{
				"c": "d",
				"e": "f",
			},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if err := parseYamlOrJson(tt.args.source, tt.args.dst); (err != nil) != tt.wantErr {
				t.Errorf("parseYamlOrJson() error = %v, wantErr %v", err, tt.wantErr)
			}
			wantString, _ := json.Marshal(tt.wantDst)
			gotString, _ := json.Marshal(tt.args.dst)
			if string(wantString) != string(gotString) {
				t.Errorf("parseYamlOrJson() parse error, wantDst %v, gotDst %v", tt.wantDst, tt.args.dst)
			}
		})
	}
}