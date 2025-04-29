from dstack.plugins._models import ApplySpec


class ApplyPolicy:
    def on_apply(self, user: str, project: str, spec: ApplySpec) -> ApplySpec:
        """
        Modify `spec` before it's applied.
        Raise `ValueError` for `spec` to be rejected as invalid.

        This method can be called twice:
          * first when a user gets a plan
          * second when a user applies a plan

        In both cases, the original spec is passed, so the method does not
        need to check if it modified the spec before.

        It's safe to modify and return `spec` without copying.
        """
        return spec


class Plugin:
    def get_apply_policies(self) -> list[ApplyPolicy]:
        return []
