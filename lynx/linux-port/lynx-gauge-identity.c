// SPDX-License-Identifier: GPL-2.0
/*
 * One-shot stock-protocol DeviceType query for Lynx's exact gauge client.
 * Preparation only; no hardware identification result yet.
 *
 * Explicitly sends only ManufacturerAccess selector 0x0001 to register 0x00,
 * waits 20 ms, then reads register 0x00, matching the OEM identification path.
 * No reset, sealing/unsealing, calibration, authentication, charger setup,
 * scanning, retries, workers, or safety interpretation. The raw identity reply
 * is cached; reading sysfs causes no further gauge transaction.
 */
#include <linux/device.h>
#include <linux/delay.h>
#include <linux/errno.h>
#include <linux/i2c.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>

#define LYNX_GAUGE_PATH "/i2c@11d04000/bq27541-battery@55"
#define LYNX_GAUGE_CONTROL 0x00
#define LYNX_DEVICE_TYPE_QUERY 0x0001

static bool allow_identity_query;
module_param(allow_identity_query, bool, 0400);
MODULE_PARM_DESC(allow_identity_query, "Explicitly allow the one fixed DeviceType query; default refuses initialization");

static struct device *sampled_device;
static int sampled_raw;

static ssize_t raw_device_type_show(struct device *dev,
					struct device_attribute *attr, char *buf)
{
	if (dev != sampled_device)
		return -ENODATA;
	return scnprintf(buf, PAGE_SIZE, "%d\n", sampled_raw);
}
static DEVICE_ATTR_RO(raw_device_type);

static struct attribute *lynx_sample_attrs[] = {
	&dev_attr_raw_device_type.attr,
	NULL,
};
ATTRIBUTE_GROUPS(lynx_sample);

static int lynx_gauge_probe(struct i2c_client *client)
{
	struct device_node *expected;
	bool matches;
	s32 value;

	if (!allow_identity_query || sampled_device)
		return -EPERM;
	expected = of_find_node_by_path(LYNX_GAUGE_PATH);
	matches = expected && client->dev.of_node == expected;
	of_node_put(expected);
	if (!matches || client->addr != 0x55 || client->adapter->nr != 7 ||
	    (client->flags & I2C_CLIENT_TEN) ||
	    !of_device_is_compatible(client->dev.of_node, "oplus,bq27541-battery") ||
	    !of_property_read_bool(client->dev.of_node, "qcom,batt_bq28z610"))
		return -ENODEV;

	/* The only command write: select the stock DeviceType information query. */
	value = i2c_smbus_write_word_data(client, LYNX_GAUGE_CONTROL,
					LYNX_DEVICE_TYPE_QUERY);
	if (value < 0) {
		dev_err(&client->dev, "LYNX_GAUGE_QUERY_FAILED error=%d\n", value);
		return value;
	}
	msleep(20);
	value = i2c_smbus_read_word_data(client, LYNX_GAUGE_CONTROL);
	if (value < 0) {
		dev_err(&client->dev, "LYNX_GAUGE_IDENTITY_READ_FAILED error=%d\n", value);
		return value;
	}
	sampled_raw = value;
	sampled_device = &client->dev;
	dev_info(&client->dev,
		 "LYNX_GAUGE_DEVICE_TYPE word=%u query=0x0001\n",
		 (unsigned int)value);
	return 0;
}

static const struct of_device_id lynx_gauge_match[] = {
	{ .compatible = "oplus,bq27541-battery" },
	{ }
};
/* Deliberately no MODULE_DEVICE_TABLE alias: never autoload this diagnostic. */

static struct i2c_driver lynx_gauge_driver = {
	.driver = {
		.name = "lynx-gauge-identity",
		.of_match_table = lynx_gauge_match,
		.dev_groups = lynx_sample_groups,
	},
	.probe_new = lynx_gauge_probe,
};

static int __init lynx_gauge_init(void)
{
	if (!allow_identity_query)
		return -EPERM;
	return i2c_add_driver(&lynx_gauge_driver);
}

static void __exit lynx_gauge_exit(void)
{
	i2c_del_driver(&lynx_gauge_driver);
	sampled_device = NULL;
}

module_init(lynx_gauge_init);
module_exit(lynx_gauge_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Lynx fixed-client one-shot stock DeviceType diagnostic");
