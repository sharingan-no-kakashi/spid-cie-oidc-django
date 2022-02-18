import logging

from collections import OrderedDict
from django.conf import settings
from typing import Union

from spid_cie_oidc.entity.policy import apply_policy

from . import settings as settings_local
from .statements import (
    get_entity_configurations,
    EntityConfiguration,
)


HTTPC_PARAMS = getattr(settings, "HTTPC_PARAMS", settings_local.HTTPC_PARAMS)
OIDCFED_MAXIMUM_AUTHORITY_HINTS = getattr(
    settings,
    "OIDCFED_MAXIMUM_AUTHORITY_HINTS",
    settings_local.OIDCFED_MAXIMUM_AUTHORITY_HINTS,
)
logger = logging.getLogger(__name__)


class TrustChainBuilder:
    """
    A trust walker that fetches statements and evaluate the evaluables

    max_intermediaries means how many hops are allowed to the trust anchor
    max_authority_hints means how much authority_hints to follow on each hop
    """

    def __init__(
        self,
        subject: str,
        trust_anchor: Union[str, EntityConfiguration],
        httpc_params: dict = {},
        max_authority_hints: int = 10,
        subject_configuration: EntityConfiguration = None,
        required_trust_marks: list = [],

        # TODO - prefetch cache
        pre_fetched_entity_configurations = {},
        pre_fetched_statements = {},
        #

        metadata_type = 'openid_provider',
        
        **kwargs,
    ) -> None:

        self.subject = subject
        self.subject_configuration = subject_configuration
        self.httpc_params = httpc_params

        self.trust_anchor = trust_anchor
        self.trust_anchor_configuration = None

        self.required_trust_marks = required_trust_marks
        self.is_valid = False

        self.statements_collection = OrderedDict()

        self.tree_of_trust = OrderedDict()
        self.trust_path = [] # list of valid subjects up to trust anchor

        self.max_authority_hints = max_authority_hints

        # dynamically valued
        self.max_path_len = 0

        self.metadata_type = metadata_type
        self.final_metadata:dict = {}

    def apply_metadata_policy(self) -> dict:
        """
            filters the trust path from subject to trust anchor
            apply the metadata policies along the path and 
            returns the final metadata
        """
        # find the path of trust
        if not self.trust_path:
            self.trust_path = [self.subject_configuration]

        logger.info(f"Applying metadata policy for {self.subject} over {self.trust_path}")
        last_path = self.tree_of_trust[len(self.trust_path)-1]

        path_found = False
        for ec in last_path:
            for sup_ec in ec.verified_by_superiors.values():
                while (len(self.trust_path) -2 <= self.max_path_len):
                    if sup_ec.sub == self.trust_anchor_configuration.sub:
                        path_found = True
                        self.trust_path.append(
                            sup_ec.verified_descendant_statements[self.subject]
                        )
                        break
                    if sup_ec.verified_by_superiors:
                        self.trust_path.append(sup_ec.sub)
                        self.apply_metadata_policy()
                    else:
                        logger.info(
                            f"'Cul de sac' in {sup_ec.sub} for {self.subject} "
                            f"to {self.trust_anchor_configuration.sub}"
                        )
                        self.trust_path = []

        # once I filtered a concrete and unique trust path I can apply the metadata policy
        if path_found:
            self.final_metadata = self.subject_configuration.payload['metadata'][self.metadata_type]
            for i in self.trust_path[1:]:
                _pol = i['metadata_policy'][self.metadata_type]
                self.final_metadata = apply_policy(self.final_metadata, _pol)
        return self.final_metadata

    def validate_last_path_to_trust_anchor(self, ec: EntityConfiguration):
        logger.info(f"Validating {self.subject} with {self.trust_anchor}")
        if self.trust_anchor_configuration.sub not in ec.verified_superiors:
            vbs = ec.validate_by_superiors(
                superiors_entity_configurations=[self.trust_anchor]
            )
        else:
            vbs = ec.verified_by_superiors

        if not vbs:
            logger.warning(f"Trust chain failed for {self.subject}")
        else:
            self.is_valid = True
            # breakpoint()
            self.apply_metadata_policy()

    def discovery(self) -> dict:
        """
        return a chain of verified statements
        from the lower up to the trust anchor
        """
        logger.info(f"Starting a Walk into Metadata Discovery for {self.subject}")
        self.tree_of_trust[0] = [self.subject_configuration]
        while (len(self.tree_of_trust) - 1) < self.max_path_len:
            last_path_n = list(self.tree_of_trust.keys())[-1]
            last_ecs = self.tree_of_trust[last_path_n]

            sup_ecs = []
            for last_ec in last_ecs:
                try:
                    superiors = last_ec.get_superiors(
                        max_authority_hints = self.max_authority_hints,
                        superiors_hints = [self.trust_anchor_configuration]
                    )
                    validated_by = last_ec.validate_by_superiors(
                        superiors_entity_configurations=superiors.values()
                    )
                    sup_ecs.extend(list(validated_by.values()))
                except Exception as e:
                    logger.exception(
                        f"Metadata discovery exception for {last_ec.sub}: {e}"
                    )

            self.tree_of_trust[last_path_n + 1] = sup_ecs

        # so we have all the intermediaries right now
        self.validate_last_path_to_trust_anchor(self.subject_configuration)

    def get_trust_anchor_configuration(self) -> None:

        if isinstance(self.trust_anchor, EntityConfiguration):
            self.trust_anchor_configuration = self.trust_anchor

        elif not self.trust_anchor_configuration and isinstance(self.trust_anchor, str):
            logger.info(f"Starting Metadata Discovery for {self.subject}")
            ta_jwt = get_entity_configurations(
                self.trust_anchor, httpc_params=self.httpc_params
            )
            self.trust_anchor_configuration = EntityConfiguration(ta_jwt)
            self.trust_anchor_configuration.validate_by_itself()

        #
        if self.trust_anchor_configuration.payload.get("constraints", {}).get(
            "max_path_length"
        ):
            self.max_path_len = int(
                self.trust_anchor_configuration.payload["constraints"][
                    "max_path_length"
                ]
            )

    def get_subject_configuration(self) -> None:
        if not self.subject_configuration:
            jwt = get_entity_configurations(
                self.subject, httpc_params=self.httpc_params
            )
            self.subject_configuration = EntityConfiguration(jwt[0])
            self.subject_configuration.validate_by_itself()

            # TODO
            # TODO: self.subject_configuration.get_valid_trust_marks()
            # valid trust marks to be compared to self.required_trust_marks

    def start(self):
        try:
            self.get_trust_anchor_configuration()
            self.get_subject_configuration()
            self.discovery()
        except Exception as e:
            self.is_valid = False
            logger.error(f"{e}")
            raise e


def trust_chain_builder(
    subject: str,
    trust_anchor: EntityConfiguration,
    httpc_params: dict = {},
    required_trust_marks: list = [],
    metadata_type: str = 'openid_provider',
) -> TrustChainBuilder:
    """
    Minimal Provider Discovery endpoint request processing

    metadata_type MUST be one of
        openid_provider
        openid_relying_party
        oauth_resource
    """
    tc = TrustChainBuilder(
        subject,
        trust_anchor=trust_anchor,
        required_trust_marks=required_trust_marks,
        httpc_params=HTTPC_PARAMS,
        metadata_type = metadata_type
    )
    tc.start()

    if not tc.is_valid:
        logger.error(
            "The tree of trust cannot be validated for "
            f"{tc.subject}: {tc.tree_of_trust}"
        )
        return False
    else:
        return tc
