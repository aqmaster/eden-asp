"""
    ORG module customisations for RLPPTM

    License: MIT
"""

from collections import OrderedDict

from gluon import current, DIV, IS_EMPTY_OR, IS_IN_SET, IS_NOT_EMPTY

from core import FS, ICON, S3CRUD, S3Represent, \
                 get_filter_options, get_form_record_id, s3_fieldmethod

from ..models.org import TestProvider, TestStation, \
                         MGRINFO_STATUS, PUBLIC_REASON

# -------------------------------------------------------------------------
def add_org_tags():
    """
        Adds organisation tags as filtered components,
        for embedding in form, filtering and as report axis
    """

    s3db = current.s3db

    s3db.add_components("org_organisation",
                        org_organisation_tag = ({"name": "delivery",
                                                 "joinby": "organisation_id",
                                                 "filterby": {"tag": "DELIVERY"},
                                                 "multiple": False,
                                                 },
                                                {"name": "orgid",
                                                 "joinby": "organisation_id",
                                                 "filterby": {"tag": "OrgID"},
                                                 "multiple": False,
                                                 },
                                                ),
                        )

# -------------------------------------------------------------------------
def configure_org_tags(resource):
    """
        Configures organisation tags
            - labels
            - selectable options
            - representation
    """

    T = current.T

    from ..requests import delivery_tag_opts

    # Configure delivery-tag
    delivery_opts = delivery_tag_opts()
    component = resource.components.get("delivery")
    ctable = component.table
    field = ctable.value
    field.default = "DIRECT"
    field.label = T("Delivery##supplying")
    field.requires = IS_IN_SET(delivery_opts, zero=None)
    field.represent = lambda v, row=None: delivery_opts.get(v, "-")

# -------------------------------------------------------------------------
def organisation_create_onaccept(form):
    """
        Custom onaccept of organisations:
            - add default tags
    """

    record_id = get_form_record_id(form)
    if not record_id:
        return

    TestProvider(record_id).add_default_tags()

# -------------------------------------------------------------------------
def organisation_postprocess(form):
    """
        Post-process organisation-form
            - create or update verification

        Notes:
            - this happens in postprocess not onaccept because the relevant
              organisation type links are established only after onaccept
    """

    record_id = get_form_record_id(form)
    if not record_id:
        return

    TestProvider(record_id).update_verification()

# -------------------------------------------------------------------------
def organisation_organisation_type_onaccept(form):
    """
        Onaccept of organisation type link:
            - update verification (requirements could have changed)

        Notes:
            - workaround for bulk-imports, where the usual
              form-postprocess is not called
    """

    if current.response.s3.bulk:
        try:
            organisation_id = form.vars.organisation_id
        except AttributeError:
            return

        TestProvider(organisation_id).update_verification()

# -------------------------------------------------------------------------
def org_organisation_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    # Add organisation tags
    add_org_tags()
    TestProvider.add_components()

    # Reports configuration
    if r.method == "report":
        axes = ["facility.location_id$L3",
                "facility.location_id$L2",
                "facility.location_id$L1",
                "facility.service_site.service_id",
                (T("Project"), "project.name"),
                (T("Organization Group"), "group_membership.group_id"),
                ]

        report_options = {
            "rows": axes,
            "cols": axes,
            "fact": [(T("Number of Organizations"), "count(id)"),
                     (T("Number of Facilities"), "count(facility.id)"),
                     ],
            "defaults": {"rows": "facility.location_id$L2",
                         "cols": None,
                         "fact": "count(id)",
                         "totals": True,
                         },
            }

        s3db.configure(tablename,
                       report_options = report_options,
                       )

    # Custom onaccept to create default tags
    s3db.add_custom_callback("org_organisation",
                             "onaccept",
                             organisation_create_onaccept,
                             method = "create",
                             )

    # Custom onaccept for type links to initialize verification
    s3db.add_custom_callback("org_organisation_organisation_type",
                             "onaccept",
                             organisation_organisation_type_onaccept,
                             )

# -------------------------------------------------------------------------
def org_organisation_controller(**attr):

    T = current.T
    s3 = current.response.s3
    settings = current.deployment_settings

    # Enable bigtable features
    settings.base.bigtable = True

    # Add custom components
    current.s3db.add_components("org_organisation",
                                hrm_human_resource = {"name": "managers",
                                                      "joinby": "organisation_id",
                                                      "filterby": {"org_contact": True,
                                                                   "status": 1, # active
                                                                   },
                                                      },
                                org_verification = {"joinby": "organisation_id",
                                                    "multiple": False,
                                                    },
                                org_commission = "organisation_id",
                                )

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        auth = current.auth
        s3db = current.s3db

        resource = r.resource

        is_org_group_admin = auth.s3_has_role("ORG_GROUP_ADMIN")

        # Configure organisation tags
        configure_org_tags(resource)

        # Add invite-method for ORG_GROUP_ADMIN role
        from ..helpers import InviteUserOrg
        s3db.set_method("org_organisation",
                        method = "invite",
                        action = InviteUserOrg,
                        )

        get_vars = r.get_vars
        mine = get_vars.get("mine")
        if mine == "1":
            # Filter to managed orgs
            managed_orgs = auth.get_managed_orgs()
            if managed_orgs is True:
                query = None
            elif managed_orgs is None:
                query = FS("id") == None
            else:
                query = FS("pe_id").belongs(managed_orgs)
            if query:
                resource.add_filter(query)
        else:
            # Filter by org_group_membership
            org_group_id = get_vars.get("g")
            if org_group_id:
                if isinstance(org_group_id, list):
                    query = FS("group.id").belongs(org_group_id)
                else:
                    query = FS("group.id") == org_group_id
                resource.add_filter(query)

        record = r.record
        component_name = r.component_name
        if not r.component:
            if r.interactive:

                ltable = s3db.project_organisation
                field = ltable.project_id
                field.represent = S3Represent(lookup="project_project")

                from core import S3SQLCustomForm, \
                                 S3SQLInlineComponent, \
                                 S3SQLInlineLink, \
                                 OptionsFilter, \
                                 TextFilter

                # Custom form
                if is_org_group_admin:

                    # Show organisation type(s) and verification tag as required
                    types = S3SQLInlineLink("organisation_type",
                                            field = "organisation_type_id",
                                            search = False,
                                            label = T("Type"),
                                            multiple = settings.get_org_organisation_types_multiple(),
                                            widget = "multiselect",
                                            )
                    from ..config import TESTSTATIONS
                    from ..helpers import is_org_group
                    if record and is_org_group(record.id, TESTSTATIONS) and \
                       TestProvider(record.id).verifreq:
                        TestProvider.configure_verification(r.resource,
                                                            role = "approver",
                                                            record_id = record.id,
                                                            )
                        type_check = "verification.orgtype"
                    else:
                        type_check = None

                    # Show org groups
                    if record:
                        groups_readonly = True
                        user = auth.user
                        if user:
                            # Only OrgGroupAdmins managing this organisation can
                            # change its group memberships
                            realm = user.realms.get(auth.get_system_roles().ORG_GROUP_ADMIN)
                            groups_readonly = realm is not None and record.pe_id not in realm
                    else:
                        groups_readonly = False
                    groups = S3SQLInlineLink("group",
                                             field = "group_id",
                                             label = T("Organization Group"),
                                             multiple = False,
                                             readonly = groups_readonly,
                                             )

                    # Show projects
                    projects = S3SQLInlineLink("project",
                                               field = "project_id",
                                               label = T("Project Partner for"),
                                               cols = 1,
                                               )

                    # Show delivery-tag
                    delivery = "delivery.value"
                else:
                    groups = projects = delivery = types = type_check = None

                crud_fields = [groups,
                               "name",
                               "acronym",
                               types,
                               projects,
                               type_check,
                               delivery,
                               S3SQLInlineComponent(
                                    "contact",
                                    fields = [("", "value")],
                                    filterby = {"field": "contact_method",
                                                "options": "EMAIL",
                                                },
                                    label = T("Email"),
                                    multiple = False,
                                    name = "email",
                                    ),
                               "phone",
                               "website",
                               "logo",
                               "comments",
                               ]

                # Configure post-process to add/update verification
                crud_form = S3SQLCustomForm(*crud_fields,
                                            postprocess = organisation_postprocess,
                                            )

                # Filters
                text_fields = ["name", "acronym", "website", "phone"]
                if is_org_group_admin:
                    text_fields.extend(["email.value", "orgid.value"])
                filter_widgets = [TextFilter(text_fields,
                                             label = T("Search"),
                                             ),
                                  ]
                if is_org_group_admin:
                    filter_widgets.extend([
                        OptionsFilter(
                            "group__link.group_id",
                            label = T("Group"),
                            options = lambda: get_filter_options("org_group"),
                            ),
                        OptionsFilter(
                            "organisation_type__link.organisation_type_id",
                            label = T("Type"),
                            options = lambda: get_filter_options("org_organisation_type"),
                            ),
                        OptionsFilter(
                            "verification.mgrinfo",
                            label = T("TestSt Manager##abbr"),
                            options = OrderedDict(MGRINFO_STATUS.labels),
                            sort = False,
                            hidden = True,
                            ),
                        ])

                resource.configure(crud_form = crud_form,
                                   filter_widgets = filter_widgets,
                                   )

            # Custom list fields
            list_fields = [#"group__link.group_id",
                           "name",
                           "acronym",
                           #"organisation_type__link.organisation_type_id",
                           "website",
                           "phone",
                           #"email.value"
                           ]
            if is_org_group_admin:
                list_fields.insert(2, (T("Type"), "organisation_type__link.organisation_type_id"))
                list_fields.insert(0, (T("Organization Group"), "group__link.group_id"))
                list_fields.append((T("Email"), "email.value"))
            r.resource.configure(list_fields = list_fields,
                                    )

        elif component_name == "facility":
            if r.component_id and \
                (is_org_group_admin or \
                record and auth.s3_has_role("ORG_ADMIN", for_pe=record.pe_id)):

                # Expose obsolete-flag
                ctable = r.component.table
                field = ctable.obsolete
                field.readable = field.writable = True

        elif component_name in ("human_resource", "managers"):

            phone_label = settings.get_ui_label_mobile_phone()
            site_id = None if component_name == "managers" else "site_id"
            list_fields = ["organisation_id",
                           "person_id",
                           "job_title_id",
                           site_id,
                           (T("Email"), "person_id$email.value"),
                           (phone_label, "person_id$phone.value"),
                           "status",
                           ]

            r.component.configure(list_fields = list_fields,
                                  )

        elif component_name == "commission":

            role = "approver" if is_org_group_admin else "applicant"
            TestProvider.configure_commission(r.component,
                                              role = role,
                                              record_id = r.id,
                                              commission_id = r.component_id,
                                              )

        return result
    s3.prep = prep

    # Custom rheader
    from ..rheaders import rlpptm_org_rheader
    attr["rheader"] = rlpptm_org_rheader

    return attr

# -------------------------------------------------------------------------
def org_organisation_type_resource(r, tablename):

    T = current.T
    db = current.db
    s3db = current.s3db

    s3db.add_components("org_organisation_type",
                        org_organisation_type_tag = ({"name": "group",
                                                      "joinby": "organisation_type_id",
                                                      "filterby": {"tag": "OrgGroup"},
                                                      "multiple": False,
                                                      },
                                                     # Commercial provider type
                                                     {"name": "commercial",
                                                      "joinby": "organisation_type_id",
                                                      "filterby": {"tag": "Commercial"},
                                                      "multiple": False,
                                                      },
                                                     # Manager info required
                                                     {"name": "minforeq",
                                                      "joinby": "organisation_type_id",
                                                      "filterby": {"tag": "MINFOREQ"},
                                                      "multiple": False,
                                                      },
                                                     # Type verification required
                                                     {"name": "verifreq",
                                                      "joinby": "organisation_type_id",
                                                      "filterby": {"tag": "VERIFREQ"},
                                                      "multiple": False,
                                                      },
                                                     ),
                        )

    if r.tablename == "org_organisation_type":

        T = current.T

        resource = r.resource
        component = resource.components.get("group")
        if component:

            # Look up organisation group names
            gtable = s3db.org_group
            groups = db(gtable.deleted == False).select(gtable.name,
                                                        cache = s3db.cache,
                                                        )
            options = [group.name for group in groups]

            # Configure them as options for the OrgGroup tag
            ctable = component.table
            field = ctable.value
            field.label = T("Organization Group")
            field.requires = IS_EMPTY_OR(IS_IN_SET(options))

        # Configure binary tag representation
        from ..helpers import configure_binary_tags
        configure_binary_tags(r.resource, ("commercial", "verifreq", "minforeq"))

        # Expose orderable item categories
        ltable = s3db.req_requester_category
        field = ltable.item_category_id
        field.represent = S3Represent(lookup="supply_item_category")

        # Custom form
        from core import S3SQLCustomForm, S3SQLInlineLink
        crud_form = S3SQLCustomForm("name",
                                    "group.value",
                                    (T("Commercial Providers"), "commercial.value"),
                                    (T("Verification required"), "verifreq.value"),
                                    (T("Manager Information required"), "minforeq.value"),
                                    S3SQLInlineLink("item_category",
                                                    field = "item_category_id",
                                                    label = T("Orderable Item Categories"),
                                                    ),
                                    "comments",
                                    )

        # Include tags and orderable item categories in list view
        list_fields = ["id",
                       "name",
                       "group.value",
                       (T("Commercial Providers"), "commercial.value"),
                       (T("Orderable Item Categories"), "requester_category.item_category_id"),
                       "comments",
                       ]

        resource.configure(crud_form = crud_form,
                           list_fields = list_fields,
                           )

# -------------------------------------------------------------------------
def check_blocked_l2(form, variable):
    """
        Checks if the L2 in a facility form is currently blocked
        for new registrations, and sets a form error if so

        Args:
            form: the FORM
            variable: the corresponding L2 variable of the location selector
    """

    if current.auth.s3_has_role("ADMIN"):
        # Admins bypass the check
        return

    try:
        district = form.vars[variable]
    except (AttributeError, KeyError):
        return

    blacklist = current.deployment_settings.get_custom("registration_blocked")

    if district and blacklist:

        ltable = current.s3db.gis_location
        query = (ltable.id == district)
        row = current.db(query).select(ltable.name, limitby=(0, 1)).first()
        if row and row.name in blacklist:
            form.errors[variable] = current.T("Due to excess capacities, no new test facilities can be registered in this district currently")

# -------------------------------------------------------------------------
def facility_create_onvalidation(form):
    """
        Onvalidation of new facility:
            - check if L2 is currently blocked for new registrations

        Args:
            form: the FORM
    """

    check_blocked_l2(form, "location_id_L2")

# -------------------------------------------------------------------------
def facility_create_onaccept(form):
    """
        Onaccept of new facility:
            - generate facility ID (code)
            - set default values for workflow tags

        Args:
            form: the FORM
    """

    record_id = get_form_record_id(form)
    if not record_id:
        return

    # Generate facility ID
    ts = TestStation(facility_id=record_id)
    ts.add_facility_code()
    if current.response.s3.bulk:
        # Postprocess not called during imports
        # => call approval update manually
        ts.update_approval()

# -------------------------------------------------------------------------
def facility_postprocess(form):
    """
        Postprocess the facility form
            - Update workflow tags

        Args:
            form: the FORM
    """

    record_id = get_form_record_id(form)
    if not record_id:
        return

    # Add/update approval workflow tags
    TestStation(facility_id=record_id).update_approval()

# -------------------------------------------------------------------------
def facility_mgrinfo(row):
    """
        Field method to determine the MGRINFO status of the organisation

        Args:
            row: the facility Row

        Returns:
            the value of the MGRINFO tag of the organisation
    """

    if hasattr(row, "org_verification"):
        # Provided as extra-field
        tag = row.org_verification.mgrinfo

    else:
        # Must look up
        db = current.db
        s3db = current.s3db
        vtable = s3db.org_verification
        query = (vtable.organisation_id == row.org_facility.organisation_id) & \
                (vtable.deleted == False)
        row = db(query).select(vtable.mgrinfo,
                               limitby = (0, 1),
                               ).first()
        tag = row.mgrinfo if row else None

    return tag

# -------------------------------------------------------------------------
def configure_facility_form(r, is_org_group_admin=False):
    """
        Configures the facility management form

        Args:
            r: the current CRUD request
            is_org_group_admin: whether the user is ORG_GROUP_ADMIN
    """

    T = current.T
    s3db = current.s3db

    organisation = obsolete = services = documents = None

    resource = r.resource
    if r.tablename == "org_facility":
        # Primary controller
        fresource = resource
        record_id = r.id
    elif r.tablename == "org_organisation" and \
            r.component_name == "facility":
        # Facility tab of organisation
        fresource = resource.components.get("facility")
        record_id = r.component_id
        obsolete = "obsolete"
    else:
        # Other view
        fresource = record_id = None


    from core import S3SQLCustomForm, \
                     S3SQLInlineComponent, \
                     S3SQLInlineLink, \
                     WithAdvice

    visible_tags = None
    if fresource:
        # Inline service selector and documents
        services = S3SQLInlineLink(
                        "service",
                        label = T("Services"),
                        field = "service_id",
                        widget = "groupedopts",
                        cols = 1,
                        )
        documents = S3SQLInlineComponent(
                        "document",
                        name = "file",
                        label = T("Documents"),
                        fields = ["name", "file", "comments"],
                        filterby = {"field": "file",
                                    "options": "",
                                    "invert": True,
                                    },
                        )

        if is_org_group_admin:
            # Approver perspective
            role = "approver"

            # Show organisation
            organisation = "organisation_id"
        else:
            # Applicant perspective
            role = "applicant"

            # Add Intros for services and documents
            services = WithAdvice(services,
                                  text = ("org", "facility", "SiteServiceIntro"),
                                  )
            documents = WithAdvice(documents,
                                   text = ("org", "facility", "SiteDocumentsIntro"),
                                   )
        if record_id:
            visible_tags = TestStation.configure_site_approval(fresource,
                                                               role = role,
                                                               record_id = record_id,
                                                               )

    crud_fields = [organisation,
                   # -- Facility
                   "name",
                   "code",
                   S3SQLInlineLink(
                       "facility_type",
                       label = T("Facility Type"),
                       field = "facility_type_id",
                       widget = "groupedopts",
                       cols = 3,
                       ),
                   # -- Address
                   "location_id",
                   # -- Service Offer
                   (T("Opening Hours"), "opening_times"),
                   "site_details.service_mode_id",
                   services,
                   # -- Appointments and Contact
                   (T("Telephone"), "phone1"),
                   "email",
                   "website",
                   (T("Appointments via"), "site_details.booking_mode_id"),
                   "comments",
                   # -- Administrative
                   documents,
                   obsolete,
                   ]

    subheadings = {"name": T("Facility"),
                   "location_id": T("Address"),
                   "opening_times": T("Service Offer"),
                   "phone1": T("Contact and Appointments"),
                   "filedocument": T("Administrative"),
                   }

    if visible_tags:

        table = fresource.table
        table.mgrinfo = s3_fieldmethod("mgrinfo", facility_mgrinfo,
                                       represent = MGRINFO_STATUS.represent,
                                       )
        extra_fields = ["organisation_id$verification.mgrinfo"]

        if is_org_group_admin:
            # Include MGRINFO status
            from core import S3SQLVirtualField
            crud_fields.append(S3SQLVirtualField("mgrinfo",
                                                 label = T("Documentation Test Station Manager"),
                                                 ))
            fname = "mgrinfo"
        else:
            fname = visible_tags[0].replace(".", "_")

        # Append workflow tags in separate section
        subheadings[fname] = T("Approval and Publication")
        crud_fields.extend(visible_tags)

    else:
        extra_fields = None

    # Configure postprocess to add/update workflow statuses
    crud_form = S3SQLCustomForm(*crud_fields,
                                postprocess = facility_postprocess,
                                )

    s3db.configure("org_facility",
                   crud_form = crud_form,
                   extra_fields = extra_fields,
                   subheadings = subheadings,
                   )

# -------------------------------------------------------------------------
def org_facility_resource(r, tablename):

    T = current.T
    auth = current.auth
    s3db = current.s3db
    settings = current.deployment_settings

    is_org_group_admin = current.auth.s3_has_role("ORG_GROUP_ADMIN")

    # Add tags for both orgs and sites
    add_org_tags()
    TestStation.add_site_approval()

    # Custom onvalidation to check L2 against blocked-list
    s3db.add_custom_callback("org_facility",
                             "onvalidation",
                             facility_create_onvalidation,
                             method = "create",
                             )

    # Custom onaccept to add default tags
    s3db.add_custom_callback("org_facility",
                             "onaccept",
                             facility_create_onaccept,
                             method = "create",
                             )

    if not is_org_group_admin and \
       not settings.get_custom(key="test_station_registration"):
        # If test station registration is disabled, no new test
        # facilities can be added either
        s3db.configure(tablename, insertable = False)

    # Configure fields
    in_org_controller = r.tablename == "org_organisation"
    from core import (S3SQLCustomForm,
                      S3SQLInlineLink,
                      LocationFilter,
                      S3LocationSelector,
                      OptionsFilter,
                      TextFilter,
                      s3_text_represent,
                      )

    table = s3db.org_facility

    # Custom representation of organisation_id including type
    field = table.organisation_id
    from ..helpers import OrganisationRepresent
    field.represent = OrganisationRepresent()
    field.comment = None

    # Expose code (r/o)
    field = table.code
    field.label = T("Test Station ID")
    field.readable = True
    field.writable = False

    # Configure location selector incl. Geocoder
    field = table.location_id
    # Address/Postcode are required
    # - except for OrgGroupAdmin, who need to be able to
    #   update the record even when this detail is missing
    address_required = not is_org_group_admin
    field.widget = S3LocationSelector(levels = ("L1", "L2", "L3", "L4"),
                                      required_levels = ("L1", "L2", "L3"),
                                      show_address = True,
                                      show_postcode = True,
                                      address_required = address_required,
                                      postcode_required = address_required,
                                      show_map = True,
                                      )
    current.response.s3.scripts.append("/%s/static/themes/RLP/js/geocoderPlugin.js" % r.application)

    # Custom tooltip for comments field
    field = table.comments
    if in_org_controller:
        field.comment = DIV(_class="tooltip",
                            _title="%s|%s" % (T("Comments"),
                                              T("Additional information and advice regarding facility and services"),
                                              ),
                            )
    else:
        field.writable = False
        field.comment = None

    # Custom label for obsolete-Flag
    field = table.obsolete
    field.label = T("Defunct")
    if r.interactive or r.representation == "aadata":
        field.represent = lambda v, row=None: ICON("remove") if v else ""
    else:
        from core import s3_yes_no_represent
        field.represent = s3_yes_no_represent
    field.comment = DIV(_class="tooltip",
                        _title="%s|%s" % (T("Defunct"),
                                          T("Please mark this field when the facility is no longer in operation"),
                                          ),
                        )

    # Opening times are mandatory
    # - except for OrgGroupAdmin, who need to be able to
    #   update the record even when this detail is missing
    if not is_org_group_admin:
        field = table.opening_times
        field.requires = IS_NOT_EMPTY()

    # Custom representation of service links
    stable = s3db.org_service_site
    field = stable.service_id
    from ..helpers import ServiceListRepresent
    field.represent = ServiceListRepresent(lookup = "org_service",
                                           show_link = False,
                                           )

    # Expose site details
    dtable = s3db.org_site_details
    field = dtable.booking_mode_id
    field.readable = True
    field.writable = in_org_controller

    field = dtable.service_mode_id
    field.readable = True
    field.writable = in_org_controller
    requires = field.requires
    if isinstance(requires, IS_EMPTY_OR):
        field.requires = requires.other

    field = dtable.authorisation_advice
    field.label = T("Advice")
    css = "approve-workflow"
    field.represent = lambda v, row=None: \
                        s3_text_represent(v,
                            truncate = False,
                            _class = ("%s workflow-advice" % css) if v else css,
                            )
    field.readable = True
    if is_org_group_admin:
        field.comment = DIV(_class="tooltip",
                            _title="%s|%s" % (T("Advice"),
                                              T("Instructions/advice for the test station how to proceed with regard to authorization"),
                                              ),
                            )
        field.writable = True
    else:
        field.writable = False

    # Special views
    get_vars = r.get_vars
    if is_org_group_admin and not in_org_controller:
        show_all = get_vars.get("$$all") == "1"
        show_pnd = get_vars.get("$$pending") == "1"
        show_rvw = get_vars.get("$$review") == "1"
        #show_obs = get_vars.get("$$obsolete") == "1"
    else:
        show_all = show_pnd = show_rvw = False #show_obs = False

    # Custom list fields
    list_fields = ["name",
                   #"code",
                   #"organisation_id",
                   "organisation_id$organisation_type__link.organisation_type_id",
                   (T("Telephone"), "phone1"),
                   "email",
                   "location_id$addr_street",
                   "location_id$addr_postcode",
                   "location_id$L4",
                   "location_id$L3",
                   "location_id$L2",
                   (T("Opening Hours"), "opening_times"),
                   "site_details.service_mode_id",
                   "service_site.service_id",
                   #"obsolete",
                   ]

    if show_pnd or show_rvw:
        list_fields.insert(1, "organisation_id")
    if is_org_group_admin:
        list_fields.insert(1, "code")
        if not in_org_controller:
            list_fields.insert(1, (T("Organization ID"), "organisation_id$orgid.value"))
    if show_all or in_org_controller:
        list_fields.append("obsolete")

    s3db.configure(tablename, list_fields=list_fields)

    # Custom filter widgets
    text_fields = ["name",
                   "location_id$L2",
                   "location_id$L3",
                   "location_id$L4",
                   "location_id$addr_postcode",
                   ]
    if is_org_group_admin:
        text_fields.append("code")
        if not in_org_controller:
            text_fields.append("organisation_id$orgid.value")
    filter_widgets = [
        TextFilter(text_fields,
                   label = T("Search"),
                   ),
        LocationFilter("location_id",
                       levels = ("L1", "L2", "L3", "L4"),
                       translate = False,
                       ),
        OptionsFilter("service_site.service_id",
                      label = T("Services"),
                      options = lambda: get_filter_options("org_service"),
                      cols = 1,
                      hidden = True,
                      ),
        ]

    if is_org_group_admin:
        from ..requests import delivery_tag_opts
        delivery_opts = delivery_tag_opts()
        filter_widgets.extend([
            OptionsFilter("organisation_id$delivery.value",
                          label = T("Delivery##supplying"),
                          options = delivery_opts,
                          hidden = True,
                          ),
            OptionsFilter("organisation_id$organisation_type__link.organisation_type_id",
                          hidden = True,
                          options = lambda: get_filter_options("org_organisation_type",
                                                               translate = True,
                                                               ),
                          ),
            ])

        if show_pnd:
            filter_widgets.extend([
                OptionsFilter("approval.public_reason",
                              label = T("Reason for unlisting"),
                              options = OrderedDict(PUBLIC_REASON.labels),
                              ),
                ])

        if show_all or r.method == "report":
            binary_tag_opts = OrderedDict([("Y", T("Yes")), ("N", T("No"))])
            if not show_all:
                default_public, default_obsolete = "Y", "False"
            else:
                default_public = default_obsolete = None
            filter_widgets.extend([
                OptionsFilter("organisation_id$project_organisation.project_id",
                              options = lambda: get_filter_options("project_project"),
                              hidden = True,
                              ),
                OptionsFilter("approval.public",
                              label = T("Approved##actionable"),
                              default = default_public,
                              options = binary_tag_opts,
                              cols = 2,
                              hidden = not default_public,
                              ),
                OptionsFilter("obsolete",
                              label = T("Status"),
                              default = default_obsolete,
                              options = {True: T("Defunct"),
                                         False: T("Active"),
                                         },
                              cols = 2,
                              hidden = not default_obsolete,
                              ),
                ])

    s3db.configure(tablename, filter_widgets=filter_widgets)

    # Custom CRUD form
    record = r.record
    public_view = r.tablename == "org_facility" and \
                    (not record or
                     not auth.s3_has_permission("update", r.table, record_id=record.id))
    if public_view:
        crud_form = S3SQLCustomForm(
                "name",
                S3SQLInlineLink(
                    "facility_type",
                    label = T("Facility Type"),
                    field = "facility_type_id",
                    widget = "groupedopts",
                    cols = 3,
                    ),
                "location_id",
                (T("Opening Hours"), "opening_times"),
                "site_details.service_mode_id",
                S3SQLInlineLink(
                    "service",
                    label = T("Services"),
                    field = "service_id",
                    widget = "groupedopts",
                    cols = 1,
                    ),
                (T("Telephone"), "phone1"),
                "email",
                "website",
                (T("Appointments via"), "site_details.booking_mode_id"),
                "comments",
                )
        s3db.configure(tablename, crud_form=crud_form)
    else:
        configure_facility_form(r, is_org_group_admin=is_org_group_admin)

    # Report options
    if r.method == "report":
        axes = ["organisation_id",
                "location_id$L3",
                "location_id$L2",
                "location_id$L1",
                "service_site.service_id",
                (T("Project"), "organisation_id$project.name"),
                (T("Organization Group"), "organisation_id$group_membership.group_id"),
                "organisation_id$organisation_type__link.organisation_type_id",
                (T("Requested Items"), "req.req_item.item_id"),
                ]

        report_options = {
            "rows": axes,
            "cols": axes,
            "fact": [(T("Number of Facilities"), "count(id)"),
                     (T("List of Facilities"), "list(name)"),
                     ],
            "defaults": {"rows": "location_id$L2",
                         "cols": None,
                         "fact": "count(id)",
                         "totals": True,
                         },
            }

        s3db.configure(tablename,
                       report_options = report_options,
                       )

    # Custom method to produce KV report
    from ..helpers import TestFacilityInfo
    s3db.set_method("org_facility",
                    method = "info",
                    action = TestFacilityInfo,
                    )


# -------------------------------------------------------------------------
def org_facility_controller(**attr):

    T = current.T
    s3 = current.response.s3
    settings = current.deployment_settings

    auth = current.auth
    is_org_group_admin = auth.s3_has_role("ORG_GROUP_ADMIN")

    # Load model for default CRUD strings
    current.s3db.table("org_facility")

    # Add approval workflow components
    if is_org_group_admin:
        TestStation.add_site_approval()

    # Custom prep
    standard_prep = s3.prep
    def prep(r):

        # Restrict data formats
        from ..helpers import restrict_data_formats
        restrict_data_formats(r)

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        s3db = current.s3db

        resource = r.resource
        table = resource.table
        record = r.record

        if not record:
            # Filter out defunct facilities
            #resource.add_filter(FS("obsolete") == False)

            # Open read-view first, even if permitted to edit
            settings.ui.open_read_first = True

            if is_org_group_admin and r.method == "report":
                s3.crud_strings["org_facility"].title_report = T("Facilities Statistics")
            else:
                get_vars = r.get_vars
                if is_org_group_admin:
                    show_all = get_vars.get("$$all") == "1"
                    show_pnd = get_vars.get("$$pending") == "1"
                    show_rvw = get_vars.get("$$review") == "1"
                    show_obs = get_vars.get("$$obsolete") == "1"
                else:
                    show_all = show_pnd = show_rvw = show_obs = False

                public_list = False
                title_list = T("Find Test Station")
                query = None
                if show_all:
                    title_list = T("All Test Stations")
                elif show_pnd:
                    title_list = T("Unapproved Test Stations")
                    query = (FS("approval.public") == "N")
                elif show_rvw:
                    title_list = T("Test Stations to review")
                    query = (FS("approval.status") == "REVIEW")
                elif show_obs:
                    title_list = T("Defunct Test Stations")
                    query = (FS("obsolete") == True)
                else:
                    public_list = True
                    query = (FS("approval.public") == "Y")

                if query:
                    resource.add_filter(query)
                if not (show_all or show_obs):
                    resource.add_filter(FS("obsolete") == False)

                if public_list:
                    if not is_org_group_admin:
                        # No Side Menu
                        current.menu.options = None

                    # Filter list by project code
                    # - re-use last used $$code filter of this session
                    # - default to original subset for consistency in bookmarks/links
                    session_s3 = current.session.s3
                    default_filter = session_s3.get("rlp_facility_filter", "TESTS-SCHOOLS")
                    code = r.get_vars.get("$$code", default_filter)
                    if code:
                        session_s3.rlp_facility_filter = code
                        query = FS("~.organisation_id$project.code") == code
                        resource.add_filter(query)
                        if code == "TESTS-SCHOOLS":
                            title_list = T("Test Stations for School and Child Care Staff")
                        elif code == "TESTS-PUBLIC":
                            title_list = T("Test Stations for Everybody")

                s3.crud_strings["org_facility"].title_list = title_list

        elif r.representation == "plain":
            # Bypass REST method, return map popup directly
            from ..helpers import facility_map_popup
            result = {"bypass": True,
                      "output": facility_map_popup(record),
                      }
        else:
            # Single facility read view

            # No facility details editable here except comments
            for fn in table.fields:
                if fn != "comments":
                    table[fn].writable = False

            # No side menu except for OrgGroupAdmin
            if not is_org_group_admin:
                current.menu.options = None

            if not is_org_group_admin and \
                not auth.s3_has_role("ORG_ADMIN", for_pe=record.pe_id):

                s3.hide_last_update = True

                field = table.obsolete
                field.readable = field.writable = False

                field = table.organisation_id
                field.represent = s3db.org_OrganisationRepresent(show_link=False)

        resource.configure(summary = ({"name": "table",
                                       "label": "Table",
                                       "widgets": [{"method": "datatable"}]
                                       },
                                       {"name": "map",
                                       "label": "Map",
                                       "widgets": [{"method": "map", "ajax_init": True}],
                                       },
                                      ),
                           insertable = False,
                           deletable = False,
                           )

        return result
    s3.prep = prep

    standard_postp = s3.postp
    def postp(r, output):

        if r.representation == "plain" and r.record:
            # Prevent standard postp rewriting output
            pass
        elif callable(standard_postp):
            output = standard_postp(r, output)

        if not is_org_group_admin and \
            r.record and isinstance(output, dict):
            # Override list-button to go to summary
            buttons = output.get("buttons")
            if isinstance(buttons, dict) and "list_btn" in buttons:
                summary = r.url(method="summary", id="", component="")
                buttons["list_btn"] = S3CRUD.crud_button(label = T("List Facilities"),
                                                         _href = summary,
                                                         )
        return output
    s3.postp = postp

    # No rheader
    if is_org_group_admin:
        from ..rheaders import rlpptm_org_rheader
        attr["rheader"] = rlpptm_org_rheader
    else:
        attr["rheader"] = None

    return attr

# END =========================================================================
