"""
    CR module customisations for MRCMS

    License: MIT
"""

from gluon import current, URL, \
                  A, DIV, H2, H3, H4, P, TABLE, TAG, TR, TD, XML, HR

from core import IS_ONE_OF, S3CRUD, PresenceRegistration

# -------------------------------------------------------------------------
def client_site_status(person_id, site_id, site_type, case_status):
    """
        Check whether a person to register at a site is a resident,
        whether they are permitted to enter/leave premises, and whether
        there are advice/instructions to the reception staff

        Args:
            person_id: the person ID
            site_id: the site ID
            site_type: the site type (tablename)
            case_status: the current case status (Row)
        Returns:
            dict, see person_site_status
    """

    T = current.T

    db = current.db
    s3db = current.s3db

    result = {"valid": False,
              "allowed_in": False,
              "allowed_out": False,
              }

    if case_status.is_closed:
        result["error"] = T("Closed case")
        return result

    if site_type == "cr_shelter":
        # Check for a shelter registration
        stable = s3db.cr_shelter
        rtable = s3db.cr_shelter_registration
        query = (stable.site_id == site_id) & \
                (stable.id == rtable.shelter_id) & \
                (rtable.person_id == person_id) & \
                (rtable.deleted != True)
        registration = db(query).select(rtable.id,
                                        rtable.registration_status,
                                        limitby=(0, 1),
                                        ).first()
        if not registration or registration.registration_status == 3:
            # No registration with this site, or checked-out
            return result

    result["valid"] = True

    # Get the current presence status at the site
    from core import SitePresence
    presence = SitePresence.status(person_id, site_id)[0]

    allowed_in = True
    allowed_out = True

    # Check if we have any case flag to deny passage and/or to show instructions
    ftable = s3db.dvr_case_flag
    ltable = s3db.dvr_case_flag_case
    query = (ltable.person_id == person_id) & \
            (ltable.deleted != True) & \
            (ftable.id == ltable.flag_id) & \
            (ftable.deleted != True)
    flags = db(query).select(ftable.name,
                             ftable.deny_check_in,
                             ftable.deny_check_out,
                             ftable.advise_at_check_in,
                             ftable.advise_at_check_out,
                             ftable.advise_at_id_check,
                             ftable.instructions,
                             )
    info = []
    append = info.append
    for flag in flags:
        # Deny IN/OUT?
        if flag.deny_check_in:
            allowed_in = False
        if flag.deny_check_out:
            allowed_out = False

        # Show flag instructions?
        if flag.advise_at_id_check:
            advise = True
        elif presence == "IN":
            advise = flag.advise_at_check_out
        elif presence == "OUT":
            advise = flag.advise_at_check_in
        else:
            advise = flag.advise_at_check_in or flag.advise_at_check_out
        if advise:
            instructions = flag.instructions
            if instructions is not None:
                instructions = instructions.strip()
            if not instructions:
                instructions = current.T("No instructions for this flag")
            append(DIV(H4(T(flag.name)),
                       P(instructions),
                       _class="checkpoint-instructions",
                       ))
    if info:
        result["info"] = DIV(_class="checkpoint-advise", *info)

    result["allowed_in"] = allowed_in
    result["allowed_out"] = allowed_out

    return result

# -------------------------------------------------------------------------
def staff_site_status(person_id, organisation_ids):
    """
        Check whether a person to register at a site is a staff member

        Args:
            person_id: the person ID
            organisation_ids: IDs of all valid staff organisations for the site
        Returns:
            dict, see person_site_status
    """

    db = current.db
    s3db = current.s3db

    htable = s3db.hrm_human_resource
    query = (htable.person_id == person_id) & \
            (htable.organisation_id.belongs(organisation_ids)) & \
            (htable.status == 1) & \
            (htable.deleted == False)
    staff = db(query).select(htable.id, limitby=(0, 1)).first()

    valid = True if staff else False

    result = {"valid": valid,
              "allowed_in": valid,
              "allowed_out": valid,
              }
    return result

# -------------------------------------------------------------------------
def person_site_status(site_id, person):
    """
        Determine the current status of a person with regard to
        entering/leaving a site

        Args:
            site_id: the site ID
            person: the person record
        Returns:
            dict {"valid": Person can be registered in/out at the site,
                  "error": Error message for the above,
                  "allowed_in": Person is allowed to enter the site,
                  "allowed_out": Person is allowed to leave the site,
                  "info": Instructions for reception staff,
                  }
    """

    T = current.T

    db = current.db
    s3db = current.s3db

    result = {"valid": False,
              "allowed_in": False,
              "allowed_out": False,
              }
    person_id = person.id

    # Get the site type and managing organisation(s)
    otable = s3db.org_organisation
    stable = s3db.org_site
    join = otable.on(otable.id == stable.organisation_id)
    row = db(stable.site_id == site_id).select(stable.instance_type,
                                               otable.id,
                                               otable.root_organisation,
                                               otable.pe_id,
                                               join = join,
                                               limitby = (0, 1),
                                               ).first()
    if not row:
        result["error"] = T("Invalid site")
        return result

    site = row.org_site
    organisation = row.org_organisation

    organisation_ids = [organisation.id]

    root_org = organisation.root_organisation
    if root_org and root_org != organisation.id:
        # Include all parent organisations
        pe_ids = s3db.pr_get_ancestors(organisation.pe_id)
        rows = db((otable.pe_id.belongs(pe_ids))).select(otable.id)
        organisation_ids += [row.id for row in rows]

    # Check for case
    ctable = s3db.dvr_case
    cstable = s3db.dvr_case_status
    query = (ctable.person_id == person_id) & \
            (ctable.organisation_id.belongs(organisation_ids)) & \
            (cstable.id == ctable.status_id)
    case = db(query).select(ctable.id,
                            cstable.is_closed,
                            limitby = (0, 1),
                            ).first()

    if case.dvr_case.id:
        # Is a client
        result.update(client_site_status(person_id,
                                         site_id,
                                         site.instance_type,
                                         case.dvr_case_status,
                                         ))
        if not result["valid"] and not result.get("error"):
            result["error"] = T("Not currently a resident")
    else:
        # May be a staff member
        result.update(staff_site_status(person_id,
                                        organisation_ids,
                                        ))
        if not result["valid"] and not result.get("error"):
            result["error"] = T("Neither currently a resident nor active staff member")

    return result

# -------------------------------------------------------------------------
def on_site_presence_event(site_id, person_id):
    """
        Update last_seen_on in case file when a site presence event
        is registered (if the person has a case file)

        Args:
            site_id: the site_id of the shelter
            person_id: the person_id to check-in
    """

    db = current.db
    s3db = current.s3db

    ctable = s3db.dvr_case
    query = (ctable.person_id == person_id) & \
            (ctable.deleted == False)
    if db(query).select(ctable.id, limitby=(0, 1)).first():
        current.s3db.dvr_update_last_seen(person_id)

# -------------------------------------------------------------------------
def cr_shelter_resource(r, tablename):

    s3db = current.s3db

    # Configure components to inherit realm_entity from the shelter
    # upon forced realm update
    s3db.configure("cr_shelter",
                   realm_components = ("shelter_unit",
                                       ),
                   )

# -------------------------------------------------------------------------
def cr_shelter_controller(**attr):

    T = current.T
    s3 = current.response.s3

    settings = current.deployment_settings

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):
        # Call standard prep
        if callable(standard_prep):
            result = standard_prep(r)
        else:
            result = True

        if r.method == "presence":
            # Configure presence event callbacks
            current.s3db.configure("cr_shelter",
                                   site_presence_in = on_site_presence_event,
                                   site_presence_out = on_site_presence_event,
                                   site_presence_seen = on_site_presence_event,
                                   site_presence_status = person_site_status,
                                   )

        else:
            if r.record and r.method == "profile":
                # Add PoI layer to the Map
                s3db = current.s3db
                ftable = s3db.gis_layer_feature
                query = (ftable.controller == "gis") & \
                        (ftable.function == "poi")
                layer = current.db(query).select(ftable.layer_id,
                                                 limitby = (0, 1)
                                                 ).first()
                try:
                    layer_id = layer.layer_id
                except AttributeError:
                    # No suitable prepop found
                    pass
                else:
                    pois = {"active": True,
                            "layer_id": layer_id,
                            "name": current.T("Buildings"),
                            "id": "profile-header-%s-%s" % ("gis_poi", r.id),
                            }
                    profile_layers = s3db.get_config("cr_shelter", "profile_layers")
                    profile_layers += (pois,)
                    s3db.configure("cr_shelter",
                                   profile_layers = profile_layers,
                                   )
            else:
                has_role = current.auth.s3_has_role
                if has_role("SECURITY") and not has_role("ADMIN"):
                    # Security can access nothing in cr/shelter except
                    # Dashboard and Check-in/out UI
                    current.auth.permission.fail()

            if r.interactive:

                resource = r.resource
                resource.configure(filter_widgets = None,
                                   insertable = False,
                                   deletable = False,
                                   )

        if not r.component:
            # Open shelter basic details in read mode
            settings.ui.open_read_first = True

        elif r.component_name == "shelter_unit":
            # Expose "transitory" flag for housing units
            utable = current.s3db.cr_shelter_unit
            field = utable.transitory
            field.readable = field.writable = True

            # Custom list fields
            list_fields = [(T("Name"), "name"),
                           "transitory",
                           "capacity",
                           "population",
                           "blocked_capacity",
                           "available_capacity",
                           ]
            r.component.configure(list_fields=list_fields)

        return result
    s3.prep = custom_prep

    # Custom postp
    standard_postp = s3.postp
    def custom_postp(r, output):
        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        # Hide side menu and rheader for presence registration
        if r.method == "presence":
            current.menu.options = None
            if isinstance(output, dict):
                output["rheader"] = ""
            return output

        # Custom view for shelter inspection
        if r.method == "inspection":
            from core import CustomController
            CustomController._view("MRCMS", "shelter_inspection.html")
            return output

        record = r.record

        # Add presence registration button, if permitted
        if record and not r.component and \
            PresenceRegistration.permitted("cr_shelter", record) and \
            isinstance(output, dict) and "buttons" in output:

            buttons = output["buttons"]

            # Add a "Presence Registration"-button
            presence_url = URL(c="cr", f="shelter", args=[record.id, "presence"])
            presence_btn = S3CRUD.crud_button(T("Presence Registration"), _href=presence_url)

            delete_btn = buttons.get("delete_btn")
            buttons["delete_btn"] = TAG[""](presence_btn, delete_btn) \
                                    if delete_btn else presence_btn

        return output
    s3.postp = custom_postp

    from ..rheaders import mrcms_cr_rheader
    attr = dict(attr)
    attr["rheader"] = mrcms_cr_rheader

    return attr

# -------------------------------------------------------------------------
def cr_shelter_registration_resource(r, tablename):

    table = current.s3db.cr_shelter_registration
    field = table.shelter_unit_id

    # Filter to available housing units
    from gluon import IS_EMPTY_OR
    field.requires = IS_EMPTY_OR(IS_ONE_OF(current.db, "cr_shelter_unit.id",
                                           field.represent,
                                           filterby = "status",
                                           filter_opts = (1,),
                                           orderby = "shelter_id",
                                           ))

# -------------------------------------------------------------------------
def cr_shelter_registration_controller(**attr):
    """
        Shelter Registration controller is just used
        by the Quartiermanager role.
    """

    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):
        # Call standard prep
        if callable(standard_prep):
            result = standard_prep(r)
        else:
            result = True

        if r.method == "assign":

            from ..helpers import get_default_shelter

            # Prep runs before split into create/update (Create should never happen in Village)
            table = r.table
            shelter_id = get_default_shelter()
            if shelter_id:
                # Only 1 Shelter
                f = table.shelter_id
                f.default = shelter_id
                f.writable = False # f.readable kept as True for cr_shelter_registration_onvalidation
                f.comment = None

            # Only edit for this Person
            f = table.person_id
            f.default = r.get_vars["person_id"]
            f.writable = False
            f.comment = None
            # Registration status hidden
            f = table.registration_status
            f.readable = False
            f.writable = False
            # Check-in dates hidden
            f = table.check_in_date
            f.readable = False
            f.writable = False
            f = table.check_out_date
            f.readable = False
            f.writable = False

            # Go back to the list of residents after assigning
            current.s3db.configure("cr_shelter_registration",
                                   create_next = URL(c="dvr", f="person"),
                                   update_next = URL(c="dvr", f="person"),
                                   )

        return result
    s3.prep = custom_prep

    return attr


# -------------------------------------------------------------------------
def profile_header(r):
    """
        Profile Header for Shelter Profile page
    """

    T = current.T
    db = current.db
    s3db = current.s3db

    rtable = s3db.cr_shelter_registration
    utable = s3db.cr_shelter_unit
    ctable = s3db.dvr_case
    stable = s3db.dvr_case_status

    record = r.record
    if not record:
        return ""

    shelter_id = record.id

    # Get nostats flags
    ftable = s3db.dvr_case_flag
    query = (ftable.nostats == True) & \
            (ftable.deleted == False)
    rows = db(query).select(ftable.id)
    nostats = set(row.id for row in rows)

    # Get person_ids with nostats-flags
    # (=persons who are registered as residents, but not BEA responsibility)
    if nostats:
        ltable = s3db.dvr_case_flag_case
        query = (ltable.flag_id.belongs(nostats)) & \
                (ltable.deleted == False)
        rows = db(query).select(ltable.person_id)
        exclude = set(row.person_id for row in rows)
    else:
        exclude = set()

    # Count total shelter registrations for non-BEA persons
    query = (rtable.person_id.belongs(exclude)) & \
            (rtable.shelter_id == shelter_id) & \
            (rtable.deleted != True)
    other_total = db(query).count()

    # Count number of shelter registrations for this shelter,
    # grouped by transitory-status of the housing unit
    left = utable.on(utable.id == rtable.shelter_unit_id)
    query = (~(rtable.person_id.belongs(exclude))) & \
            (rtable.shelter_id == shelter_id) & \
            (rtable.deleted != True)
    count = rtable.id.count()
    rows = db(query).select(utable.transitory,
                            count,
                            groupby = utable.transitory,
                            left = left,
                            )
    transitory = 0
    regular = 0
    for row in rows:
        if row[utable.transitory]:
            transitory += row[count]
        else:
            regular += row[count]
    total = transitory + regular

    # Children
    from dateutil.relativedelta import relativedelta
    EIGHTEEN = r.utcnow - relativedelta(years=18)
    ptable = s3db.pr_person
    query = (ptable.date_of_birth > EIGHTEEN) & \
            (~(ptable.id.belongs(exclude))) & \
            (ptable.id == rtable.person_id) & \
            (rtable.shelter_id == shelter_id)
    count = ptable.id.count()
    row = db(query).select(count).first()
    children = row[count]

    CHILDREN = TR(TD(T("Children")),
                  TD(children),
                  )

    # Families on-site
    gtable = s3db.pr_group
    mtable = s3db.pr_group_membership
    join = [mtable.on((~(mtable.person_id.belongs(exclude))) & \
                      (mtable.group_id == gtable.id) & \
                      (mtable.deleted != True)),
            rtable.on((rtable.person_id == mtable.person_id) & \
                      (rtable.shelter_id == shelter_id) & \
                      (rtable.deleted != True)),
            ]
    query = (gtable.group_type == 7) & \
            (gtable.deleted != True)

    rows = db(query).select(gtable.id,
                            having = (mtable.id.count() > 1),
                            groupby = gtable.id,
                            join = join,
                            )
    families = len(rows)
    FAMILIES = TR(TD(T("Families")),
                  TD(families),
                  )

    TOTAL = TR(TD(T("Current Population##shelter")),
               TD(total),
               _class="dbstats-total",
               )
    TRANSITORY = TR(TD(T("in staging area")),
                    TD(transitory),
                    _class="dbstats-sub",
                    )
    REGULAR = TR(TD(T("in housing units")),
                 TD(regular),
                 _class="dbstats-sub",
                 )

    #OTHER = TR(TD(T("Population Other")),
    #           TD(other_total),
    #           _class="dbstats-extra",
    #           )

    # Get the IDs of open case statuses
    query = (stable.is_closed == False) & (stable.deleted != True)
    rows = db(query).select(stable.id)
    OPEN = set(row.id for row in rows)

    # Count number of external persons
    ftable = s3db.dvr_case_flag
    ltable = s3db.dvr_case_flag_case
    left = [ltable.on((ltable.flag_id == ftable.id) & \
                      (ltable.deleted != True)),
            ctable.on((ctable.person_id == ltable.person_id) & \
                      (~(ctable.person_id.belongs(exclude))) & \
                      (ctable.status_id.belongs(OPEN)) & \
                      ((ctable.archived == False) | (ctable.archived == None)) & \
                      (ctable.deleted != True)),
            rtable.on((rtable.person_id == ltable.person_id) & \
                      (rtable.deleted != True)),
            ]
    query = (ftable.is_external == True) & \
            (ftable.deleted != True) & \
            (ltable.id != None) & \
            (ctable.id != None) & \
            (rtable.shelter_id == shelter_id)
    count = ctable.id.count()
    rows = db(query).select(count, left=left)
    external = rows.first()[count] if rows else 0

    EXTERNAL = TR(TD(T("External (Hospital / Police)")),
                  TD(external),
                  )

    # Get the number of free places in the BEA
    # => Non-BEA registrations do not occupy BEA capacity,
    #    so need to re-add the total here:
    free = (record.available_capacity or 0) + other_total
    FREE = TR(TD(T("Free places")),
              TD(free),
              _class="dbstats-total",
              )

    # Announcements
    from s3db.cms import S3CMS
    resource_content = S3CMS.resource_content
    announce = resource_content("cr", "shelter", shelter_id,
                                hide_if_empty=True,
                                )

    # Weather (uses fake weather module/resource)
    table = s3db.cms_post
    ltable = db.cms_post_module
    query = (ltable.module == "weather") & \
            (ltable.resource == "weather") & \
            (ltable.record == shelter_id) & \
            (ltable.post_id == table.id) & \
            (table.deleted != True)
    _item = db(query).select(table.id,
                             table.body,
                             limitby=(0, 1)).first()
    auth = current.auth
    ADMIN = auth.get_system_roles().ADMIN
    ADMIN = auth.s3_has_role(ADMIN)
    if ADMIN:
        url_vars = {"module": "weather",
                    "resource": "weather",
                    "record": shelter_id,
                    # Custom redirect after CMS edit
                    # (required for fake module/resource)
                    "url": URL(c = "cr",
                               f = "shelter",
                               args = [shelter_id, "profile"],
                               ),
                    }
        EDIT_WEATHER = T("Edit Weather Widget")
        if _item:
            item = DIV(XML(_item.body),
                       A(EDIT_WEATHER,
                         _href=URL(c="cms", f="post",
                                   args = [_item.id, "update"],
                                   vars = url_vars,
                                   ),
                         _class="action-btn cms-edit",
                         ))
        else:
            item = A(EDIT_WEATHER,
                     _href=URL(c="cms", f="post",
                               args = "create",
                               vars = url_vars,
                               ),
                     _class="action-btn cms-edit",
                     )
    elif _item:
        item = XML(_item.body)
    else:
        item = ""

    weather = DIV(item, _id="cms_weather", _class="cms_content")

    # Show Check-in/Check-out action only if user is permitted
    # to update shelter registrations (NB controllers may be
    # read-only, therefore checking against default here):
    if PresenceRegistration.permitted("cr_shelter", record.site_id):
        # Action button for presence registration
        cico = A(T("Presence Registration"),
                 _href=r.url(method="presence"),
                 _class="action-btn dashboard-action",
                 )
    else:
        cico = ""

    # Generate profile header HTML
    output = DIV(H2(record.name),
                    P(record.comments or ""),
                    H3(T("Announcements")) if announce else "",
                    announce,
                    HR(),
                    # Current population overview
                    TABLE(TR(TD(TABLE(TOTAL,
                                      TRANSITORY,
                                      REGULAR,
                                      CHILDREN,
                                      FAMILIES,
                                      EXTERNAL,
                                      FREE,
                                      #OTHER,
                                      _class="dbstats",
                                      ),
                                ),
                             TD(weather,
                                _class="show-for-large-up",
                                ),
                             ),
                          ),
                    cico,
                    _class="profile-header",
                    )

    return output

# END =========================================================================