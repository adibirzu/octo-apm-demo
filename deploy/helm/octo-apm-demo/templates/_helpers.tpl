{{/*
Common labels applied to every object this chart creates. Matches the
envsubst manifests in deploy/k8s/oke/ so resources remain compatible
with bootstrap.sh-managed clusters.
*/}}
{{- define "octo.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- with .Values.global.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{- define "octo.shop.selectorLabels" -}}
app: octo-drone-shop
{{- end -}}

{{- define "octo.crm.selectorLabels" -}}
app: enterprise-crm-portal
{{- end -}}

{{/*
Resolve a component's OCIR image. Falls back to global defaults when the
per-component override is empty.
*/}}
{{- define "octo.image" -}}
{{- $ctx := index . 0 -}}
{{- $cmp := index . 1 -}}
{{- $region := default $ctx.Values.global.image.region $cmp.image.region -}}
{{- $tenancy := default $ctx.Values.global.image.tenancy $cmp.image.tenancy -}}
{{/* Helm's --set treats purely numeric strings (e.g. timestamp tags like
     20260424230757) as int64. printf "%s" on an int prints a %!s marker
     which makes kubelet reject the image with "invalid reference format".
     Force everything through toString. */}}
{{- $tag := toString (default $ctx.Values.global.image.tag $cmp.image.tag) -}}
{{- if not $tenancy -}}
{{- fail "global.image.tenancy is required — set your OCIR namespace" -}}
{{- end -}}
{{- printf "%s.ocir.io/%s/%s:%s" (toString $region) (toString $tenancy) (toString $cmp.image.repository) $tag -}}
{{- end -}}

{{/*
Resolve FQDN for a component: "<subdomain>.<global.dnsDomain>".
*/}}
{{- define "octo.fqdn" -}}
{{- $ctx := index . 0 -}}
{{- $cmp := index . 1 -}}
{{- printf "%s.%s" $cmp.subdomain $ctx.Values.global.dnsDomain -}}
{{- end -}}

{{/*
Render a Secret only when at least one referenced value is non-empty.
Empty fields are dropped so downstream optional secretKeyRef lookups
stay truly optional.
Args: (list $name $namespace $labels $dataDict)
*/}}
{{- define "octo.secret" -}}
{{- $name := index . 0 -}}
{{- $ns := index . 1 -}}
{{- $labels := index . 2 -}}
{{- $data := index . 3 -}}
{{- $nonEmpty := dict -}}
{{- range $k, $v := $data -}}
{{- if $v -}}
{{- $_ := set $nonEmpty $k $v -}}
{{- end -}}
{{- end -}}
{{- if $nonEmpty -}}
apiVersion: v1
kind: Secret
metadata:
  name: {{ $name }}
  namespace: {{ $ns }}
  labels:
{{ toYaml $labels | indent 4 }}
type: Opaque
stringData:
{{- range $k, $v := $nonEmpty }}
  {{ $k }}: {{ $v | quote }}
{{- end }}
---
{{- end -}}
{{- end -}}
