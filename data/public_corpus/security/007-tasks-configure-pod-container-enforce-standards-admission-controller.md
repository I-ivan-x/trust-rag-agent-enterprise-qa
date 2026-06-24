---
doc_id: doc-public-k8s-0007-tasks-configure-pod-container-enforce-standards-
title: Tasks - Configure-Pod-Container - Enforce-Standards-Admission-Controller
doc_type: public_doc
status: active
version: kubernetes-website-main
created_at: null
updated_at: '2026-06-24'
effective_date: null
owner_team: Kubernetes Project
department: Public Documentation
access_level: restricted
allowed_roles:
- admin
tags:
- kubernetes
- config_violation
language: en
source_path: data/public_corpus/security/007-tasks-configure-pod-container-enforce-standards-admission-controller.md
supersedes_doc_id: null
superseded_by: null
conflict_group_id: null
is_authoritative: true
corpus_source: public_external
source_origin: public_repo
source_license_note: Kubernetes documentation from the public kubernetes/website GitHub
  repository; licensed under CC BY 4.0 and fetched verbatim with attribution.
hard_negative_group_id: null
metadata_origin: native
source_url: https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/tasks/configure-pod-container/enforce-standards-admission-controller.md
upstream_repo_path: content/en/docs/tasks/configure-pod-container/enforce-standards-admission-controller.md
upstream_original_path: content/en/docs/tasks/configure-pod-container/enforce-standards-admission-controller.md
upstream_ref: main
q3_condition_hint: CONFIG_VIOLATION
---

Kubernetes provides a built-in [admission controller](/docs/reference/access-authn-authz/admission-controllers/#podsecurity)
to enforce the [Pod Security Standards](/docs/concepts/security/pod-security-standards).
You can configure this admission controller to set cluster-wide defaults and [exemptions](/docs/concepts/security/pod-security-admission/#exemptions).

## {{% heading "prerequisites" %}}

Following an alpha release in Kubernetes v1.22,
Pod Security Admission became available by default in Kubernetes v1.23, as
a beta. From version 1.25 onwards, Pod Security Admission is generally
available.

{{% version-check %}}

If you are not running Kubernetes {{< skew currentVersion >}}, you can switch
to viewing this page in the documentation for the Kubernetes version that you
are running.

## Configure the Admission Controller

{{< note >}}
`pod-security.admission.config.k8s.io/v1` configuration requires v1.25+.
For v1.23 and v1.24, use [v1beta1](https://v1-24.docs.kubernetes.io/docs/tasks/configure-pod-container/enforce-standards-admission-controller/).
For v1.22, use [v1alpha1](https://v1-22.docs.kubernetes.io/docs/tasks/configure-pod-container/enforce-standards-admission-controller/).
{{< /note >}}

```yaml
apiVersion: apiserver.config.k8s.io/v1
kind: AdmissionConfiguration
plugins:
- name: PodSecurity
  configuration:
    apiVersion: pod-security.admission.config.k8s.io/v1 # see compatibility note
    kind: PodSecurityConfiguration
    # Defaults applied when a mode label is not set.
    #
    # Level label values must be one of:
    # - "privileged" (default)
    # - "baseline"
    # - "restricted"
    #
    # Version label values must be one of:
    # - "latest" (default) 
    # - specific version like "v{{< skew currentVersion >}}"
    defaults:
      enforce: "privileged"
      enforce-version: "latest"
      audit: "privileged"
      audit-version: "latest"
      warn: "privileged"
      warn-version: "latest"
    exemptions:
      # Array of authenticated usernames to exempt.
      usernames: []
      # Array of runtime class names to exempt.
      runtimeClasses: []
      # Array of namespaces to exempt.
      namespaces: []
```

{{< note >}}
The above manifest needs to be specified via the `--admission-control-config-file` to kube-apiserver.
{{< /note >}}
