// SPDX-License-Identifier: GPL-2.0
/*
 * One-shot raw temperature-register diagnostic for Lynx's stock DT client.
 * Preparation only: no validated hardware result yet.
 *
 * No gauge initialization/control commands, writes of data, address scanning,
 * retries, worker threads, calibration, or power-supply/thermal registration.
 * SMBus read-word includes the normal register-selector byte on the wire.
 * DT identification is not proof of the installed gauge silicon. The raw
 * value must not be used as a validated battery temperature or safety input.
 */
#include <linux/device.h>
#include <linux/errno.h>
#include <linux/i2c.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>

#define LYNX_GAUGE_PATH "/i2c@11d04000/bq27541-battery@55"
#define LYNX_GAUGE_TEMPERATURE 0x06

static bool allow_raw_read;
module_param(allow_raw_read, bool, 0400);
MODULE_PARM_DESC(allow_raw_read, "Explicitly allow one raw register sample; default refuses module initialization");

static struct device *sampled_device;
static int sampled_raw;

static ssize_t raw_temperature_word_show(struct device *dev,
					struct device_attribute *attr, char *buf)
{
	if (dev != sampled_device)
		return -ENODATA;
	return scnprintf(buf, PAGE_SIZE, "%d\n", sampled_raw);
}
static DEVICE_ATTR_RO(raw_temperature_word);

static struct attribute *lynx_sample_attrs[] = {
	&dev_attr_raw_temperature_word.attr,
	NULL,
};
ATTRIBUTE_GROUPS(lynx_sample);

static int lynx_gauge_probe(struct i2c_client *client)
{
	struct device_node *expected;
	bool matches;
	s32 value;

	if (!allow_raw_read || sampled_device)
		return -EPERM;
	expected = of_find_node_by_path(LYNX_GAUGE_PATH);
	matches = expected && client->dev.of_node == expected;
	of_node_put(expected);
	if (!matches || client->addr != 0x55 || client->adapter->nr != 7 ||
	    (client->flags & I2C_CLIENT_TEN) ||
	    !of_device_is_compatible(client->dev.of_node, "oplus,bq27541-battery") ||
	    !of_property_read_bool(client->dev.of_node, "qcom,batt_bq28z610"))
		return -ENODEV;

	/* The only gauge transaction: one standard SMBus read-word. */
	value = i2c_smbus_read_word_data(client, LYNX_GAUGE_TEMPERATURE);
	if (value < 0) {
		dev_err(&client->dev, "LYNX_GAUGE_SAMPLE_FAILED error=%d\n", value);
		return value;
	}
	sampled_raw = value;
	sampled_device = &client->dev;
	dev_info(&client->dev,
		 "LYNX_GAUGE_RAW register=0x06 word=%u model_unverified=1\n",
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
		.name = "lynx-gauge-sample",
		.of_match_table = lynx_gauge_match,
		.dev_groups = lynx_sample_groups,
	},
	.probe_new = lynx_gauge_probe,
};

static int __init lynx_gauge_init(void)
{
	if (!allow_raw_read)
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
MODULE_DESCRIPTION("Lynx fixed-client one-shot raw gauge diagnostic; model unverified");
