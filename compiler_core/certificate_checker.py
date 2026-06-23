"""Track C1: Independent certificate checker.

MUST NOT call the main evaluator. Verifies certificates against raw inputs only.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class HornCertificate:
    """Certificate proving a fact is in the Horn closure."""
    target_id: str
    proof_chain: tuple[str, ...]

    def verify(self, facts: set[str], rules: dict[str, tuple[tuple[str, ...], str]]) -> bool:
        derived: set[str] = set(facts)
        for rule_id in self.proof_chain:
            if rule_id not in rules:
                return False
            premises, head = rules[rule_id]
            if not all(p in derived for p in premises):
                return False
            derived.add(head)
        return self.target_id in derived


@dataclass(frozen=True)
class GroundedINCertificate:
    """Certificate proving an argument is IN under grounded semantics."""
    argument_id: str
    accepted_iteration: int

    def verify(self, aaf: tuple[tuple[str, ...], tuple[tuple[str, str], ...]], max_iter: int = 1000) -> bool:
        args, attacks = aaf
        attack_set = set(attacks)
        arg_set = set(args)
        if self.argument_id not in arg_set:
            return False
        grounded: set[str] = set()
        for iteration in range(1, max_iter + 1):
            newly: set[str] = set()
            for a in arg_set:
                if a in grounded:
                    continue
                attackers_of_a = {src for src, tgt in attack_set if tgt == a}
                if not attackers_of_a:
                    newly.add(a)
                elif all(any((c, b) in attack_set for c in grounded) for b in attackers_of_a):
                    newly.add(a)
            if not newly:
                break
            grounded |= newly
            if iteration == self.accepted_iteration:
                return self.argument_id in grounded
        return False


@dataclass(frozen=True)
class OUTCertificate:
    """Certificate proving an argument is OUT under grounded semantics."""
    argument_id: str
    in_attacker: str
    attacker_in_cert: GroundedINCertificate

    def verify(self, aaf: tuple[tuple[str, ...], tuple[tuple[str, str], ...]]) -> bool:
        args, attacks = aaf
        attack_set = set(attacks)
        if self.argument_id not in args:
            return False
        if (self.in_attacker, self.argument_id) not in attack_set:
            return False
        return self.attacker_in_cert.verify(aaf)


@dataclass(frozen=True)
class UNDECCertificate:
    """Certificate proving an argument is UNDEC under grounded semantics."""
    argument_id: str

    def verify(self, aaf: tuple[tuple[str, ...], tuple[tuple[str, str], ...]]) -> bool:
        args, attacks = aaf
        attack_set = set(attacks)
        if self.argument_id not in args:
            return False
        grounded_ins = self._compute_grounded(args, attack_set)
        if self.argument_id in grounded_ins:
            return False
        if any((src, self.argument_id) in attack_set and src in grounded_ins for src in args):
            return False
        return True

    @staticmethod
    def _compute_grounded(args: tuple[str, ...], attack_set: set, max_iter: int = 1000) -> set[str]:
        grounded: set[str] = set()
        for _ in range(max_iter):
            newly: set[str] = set()
            for a in args:
                if a in grounded:
                    continue
                attackers = {src for src, tgt in attack_set if tgt == a}
                if not attackers:
                    newly.add(a)
                elif all(any((c, b) in attack_set for c in grounded) for b in attackers):
                    newly.add(a)
            if not newly:
                break
            grounded |= newly
        return grounded
