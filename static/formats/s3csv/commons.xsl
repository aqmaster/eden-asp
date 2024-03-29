<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">

    <!-- **********************************************************************
         S3CSV Common Templates

         Copyright (c) 2010-15 Sahana Software Foundation

         Permission is hereby granted, free of charge, to any person
         obtaining a copy of this software and associated documentation
         files (the "Software"), to deal in the Software without
         restriction, including without limitation the rights to use,
         copy, modify, merge, publish, distribute, sublicense, and/or sell
         copies of the Software, and to permit persons to whom the
         Software is furnished to do so, subject to the following
         conditions:

         The above copyright notice and this permission notice shall be
         included in all copies or substantial portions of the Software.

         THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
         EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
         OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
         NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
         HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
         WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
         FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
         OTHER DEALINGS IN THE SOFTWARE.

    *********************************************************************** -->
    <!-- Resolve Column header

         Helper template to resolve column header variants, using both
         an external labels.xml and the <labels> subtree in the source.

         Parameter column: the standard column label
         Output: a |-delimited string of alternative column labels
    -->

    <xsl:template name="ResolveColumnHeader">

        <xsl:param name="colname"/>
        <xsl:value-of select="concat('|', $colname, '|')"/>

        <!-- Label alternatives in the source file -->
        <xsl:variable name="src" select="//labels/column[@name=$colname]"/>
        <xsl:for-each select="$src/label">
            <xsl:variable name="label" select="text()"/>
            <xsl:variable name="duplicates" select="preceding-sibling::label[text()=$label]"/>
            <xsl:if test="$label != $colname and not($duplicates)">
                <xsl:value-of select="concat($label, '|')"/>
            </xsl:if>
        </xsl:for-each>
        <!-- Label alternatives in labels.xml -->
        <xsl:variable name="labels" select="document('labels.xml')//labels"/>
        <xsl:variable name="map" select="$labels/column[@name=$colname]"/>
        <xsl:for-each select="$map/label">
            <xsl:variable name="label" select="text()"/>
            <xsl:variable name="srcdup" select="$src/label[text()=$label]"/>
            <xsl:variable name="mapdup" select="preceding-sibling::label[text()=$label]"/>
            <xsl:if test="$label != $colname and not($srcdup) and not ($mapdup)">
                <xsl:value-of select="concat($label, '|')"/>
            </xsl:if>
        </xsl:for-each>

        <!-- Column hashtags -->
        <xsl:variable name="hashtags">
            <!-- Hashtags in source file -->
            <xsl:for-each select="$src/tag">
                <xsl:variable name="tag" select="text()"/>
                <xsl:variable name="srcdup" select="preceding-sibling::tag[text()=$tag]"/>
                <xsl:if test="$tag!='' and not($srcdup)">
                    <xsl:value-of select="concat($tag, '|')"/>
                </xsl:if>
            </xsl:for-each>
            <!-- Hashtags in labels.xml -->
            <xsl:for-each select="$map/tag">
                <xsl:variable name="tag" select="text()"/>
                <xsl:variable name="srcdup" select="$src/tag[text()=$tag]"/>
                <xsl:variable name="mapdup" select="preceding-sibling::tag[text()=$tag]"/>
                <xsl:if test="$tag!='' and not($srcdup) and not($mapdup)">
                    <xsl:value-of select="concat($tag, '|')"/>
                </xsl:if>
            </xsl:for-each>
        </xsl:variable>

        <!-- Append hashtags -->
        <xsl:if test="$hashtags!=''">
            <xsl:value-of select="concat('#|', $hashtags)"/>
        </xsl:if>

    </xsl:template>

    <!-- ****************************************************************** -->
    <!-- Get Column Value

         Extracts the value of a column in the current <row> and resolves
         any option label variants, using both an external labels.xml and
         the <labels> subtree in the source.

         Parameter colhdrs: all column header variants as a |-delimited
                            string (as returned from ResolveColumnHeader)
         Output: the column value
    -->

    <xsl:template name="GetColumnValue">

        <xsl:param name="colhdrs"/>

        <!-- Column label alternatives -->
        <xsl:variable name="colLabels">
            <xsl:choose>
                <xsl:when test="contains($colhdrs, '#')">
                    <xsl:value-of select="substring-before($colhdrs, '#')"/>
                </xsl:when>
                <xsl:otherwise>
                    <xsl:value-of select="$colhdrs"/>
                </xsl:otherwise>
            </xsl:choose>
        </xsl:variable>

        <!-- Column hashtags -->
        <xsl:variable name="colTags">
            <xsl:choose>
                <xsl:when test="contains($colhdrs, '#')">
                    <xsl:value-of select="substring-after($colhdrs, '#')"/>
                </xsl:when>
            </xsl:choose>
        </xsl:variable>

        <!-- Get the column value -->
        <xsl:variable name="colValue">
            <xsl:choose>
                <xsl:when test="$colTags!='' and col[contains($colTags, concat('|', substring-after(@hashtag, '#'), '|'))][1]">
                    <xsl:value-of select="col[contains($colTags, concat('|', substring-after(@hashtag, '#'), '|'))][1]/text()"/>
                </xsl:when>
                <xsl:otherwise>
                    <xsl:value-of select="col[contains($colhdrs, concat('|', @field, '|'))][1]/text()"/>
                </xsl:otherwise>
            </xsl:choose>
        </xsl:variable>

        <!-- Variables for value mapping -->
        <xsl:variable name="colname" select="substring-before(substring-after($colLabels, '|'), '|')"/>
        <xsl:variable name="srcmap" select="//labels/column[@name=$colname]"/>
        <xsl:variable name="lblmap" select="document('labels.xml')//labels/column[@name=$colname]"/>
        <xsl:variable name="alt1" select="$srcmap/option[@name=$colValue or ./label/text()=$colValue]"/>
        <xsl:variable name="alt2" select="$lblmap/option[@name=$colValue or ./label/text()=$colValue]"/>

        <xsl:choose>
            <xsl:when test="$alt1">
                <!-- Apply value mapping from source -->
                <xsl:value-of select="$alt1[1]/@value"/>
            </xsl:when>
            <xsl:when test="$alt2">
                <!-- Apply value mapping from labels.xml -->
                <xsl:value-of select="$alt2[1]/@value"/>
            </xsl:when>
            <xsl:otherwise>
                <!-- Use value from source verbatim -->
                <xsl:value-of select="$colValue"/>
            </xsl:otherwise>
        </xsl:choose>
    </xsl:template>

    <!-- ****************************************************************** -->
    <!-- splitList: split a string with a list into items and call a
         template with the name "resource" with each item as parameter
         "item". The "resource" template is to be defined in the calling
         stylesheet.

         @param list: the string containing the list
         @param sep: the list separator
         @param arg: argument to be passed on to the "resource" template
         @param org: argument to be passed on to the "resource" template

         NB You probably want to look at xml/commons.xsl instead DUPE, DUPE, DUPE
    -->
    <xsl:template name="splitList">

        <xsl:param name="list"/>
        <xsl:param name="listsep" select="','"/>
        <xsl:param name="arg"/>
        <xsl:param name="org"/>

        <xsl:if test="$listsep">
            <xsl:choose>
                <xsl:when test="contains($list, $listsep)">
                    <xsl:variable name="head">
                        <xsl:value-of select="substring-before($list, $listsep)"/>
                    </xsl:variable>
                    <xsl:variable name="tail">
                        <xsl:value-of select="substring-after($list, $listsep)"/>
                    </xsl:variable>
                    <xsl:call-template name="resource">
                        <xsl:with-param name="item" select="normalize-space($head)"/>
                        <xsl:with-param name="arg" select="$arg"/>
                        <xsl:with-param name="org" select="$org"/>
                    </xsl:call-template>
                    <xsl:call-template name="splitList">
                        <xsl:with-param name="list" select="$tail"/>
                        <xsl:with-param name="listsep" select="$listsep"/>
                        <xsl:with-param name="arg" select="$arg"/>
                        <xsl:with-param name="org" select="$org"/>
                    </xsl:call-template>
                </xsl:when>
                <xsl:otherwise>
                    <xsl:if test="normalize-space($list)!=''">
                        <xsl:call-template name="resource">
                            <xsl:with-param name="item" select="normalize-space($list)"/>
                            <xsl:with-param name="arg" select="$arg"/>
                            <xsl:with-param name="org" select="$org"/>
                        </xsl:call-template>
                    </xsl:if>
                </xsl:otherwise>
            </xsl:choose>
        </xsl:if>

    </xsl:template>

    <!-- ****************************************************************** -->
    <!-- listString: split a string with a list into items

         @param list: the string containing the list
         @param sep: the list separator
    -->
    <xsl:template name="listString">

        <xsl:param name="list"/>
        <xsl:param name="listsep" select="','"/>

        <xsl:if test="$listsep">
            <xsl:choose>
                <xsl:when test="contains($list, $listsep)">
                    <xsl:variable name="head">
                        <xsl:value-of select="substring-before($list, $listsep)"/>
                    </xsl:variable>
                    <xsl:variable name="tail">
                        <xsl:value-of select="substring-after($list, $listsep)"/>
                    </xsl:variable>
                    <xsl:text>"</xsl:text>
                    <xsl:value-of select="normalize-space($head)"/>
                    <xsl:text>",</xsl:text>
                    <xsl:call-template name="listString">
                        <xsl:with-param name="list" select="$tail"/>
                        <xsl:with-param name="listsep" select="$listsep"/>
                    </xsl:call-template>
                </xsl:when>
                <xsl:otherwise>
                    <xsl:if test="normalize-space($list)!=''">
                        <xsl:text>"</xsl:text>
                        <xsl:value-of select="normalize-space($list)"/>
                        <xsl:text>"</xsl:text>
                    </xsl:if>
                </xsl:otherwise>
            </xsl:choose>
        </xsl:if>

    </xsl:template>

    <!-- ****************************************************************** -->
    <!-- Convert a string to uppercase

         @param string: the string
    -->

    <xsl:template name="uppercase">

        <xsl:param name="string"/>
        <xsl:value-of select="translate($string,
            'abcdefghijklmnopqrstuvwxyzáéíóúàèìòùäöüåâêîôûãẽĩõũø',
            'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÀÈÌÒÙÄÖÜÅÂÊÎÔÛÃẼĨÕŨØ')"/>
    </xsl:template>

    <!-- ****************************************************************** -->
    <!-- Helper for boolean fields

         Args:
             column: the column label
             field: the field name
             default: the value to use when the column value is empty

         Notes:
             - the field will only be imported of the column holds either
               'true' or 'false' as value, or if the column is empty but
               a default has been specified; all other cases will fall back
               to the database default (which is the preferred behavior)
    -->

    <xsl:template name="Boolean">

        <xsl:param name="column"/>
        <xsl:param name="field"/>
        <xsl:param name="default"/>

        <xsl:variable name="value" select="normalize-space(col[@field=$column]/text())"/>
        <xsl:if test="$value='true' or $value='false' or ($value='' and $default!='')">
            <data>
                <xsl:attribute name="field">
                    <xsl:value-of select="$field"/>
                </xsl:attribute>
                <xsl:attribute name="value">
                    <xsl:choose>
                        <xsl:when test="$value='true'">
                            <xsl:value-of select="'true'"/>
                        </xsl:when>
                        <xsl:when test="$value='false'">
                            <xsl:value-of select="'false'"/>
                        </xsl:when>
                        <xsl:otherwise>
                            <xsl:value-of select="$default"/>
                        </xsl:otherwise>
                    </xsl:choose>
                </xsl:attribute>
            </data>
        </xsl:if>

    </xsl:template>

    <!-- ****************************************************************** -->
    <!-- Create an organisation entry for the current row -->

    <xsl:template name="Organisation">

        <xsl:param name="Field">Organisation</xsl:param>

        <xsl:variable name="OrgName" select="col[@field=$Field]/text()"/>

        <resource name="org_organisation">
            <xsl:attribute name="tuid">
                <xsl:value-of select="$OrgName"/>
            </xsl:attribute>
            <data field="name"><xsl:value-of select="$OrgName"/></data>
        </resource>
    </xsl:template>

</xsl:stylesheet>
