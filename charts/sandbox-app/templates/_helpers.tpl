{{- define "sandbox.namespace" -}}
sbx-{{ .Values.app.name }}
{{- end -}}

{{- define "sandbox.labels" -}}
app.kubernetes.io/name: {{ .Values.app.name }}
app.kubernetes.io/managed-by: sandbox-platform
sandbox.metlife.internal/stack: {{ .Values.app.stack }}
sandbox.metlife.internal/data-classification: {{ .Values.app.dataClassification }}
{{- end -}}

{{- define "sandbox.host" -}}
{{ .Values.app.name }}.{{ .Values.platform.baseDomain }}
{{- end -}}
