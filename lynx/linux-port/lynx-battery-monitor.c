// SPDX-License-Identifier: GPL-2.0
/* Read-only ZY0603 observations after a verified same-boot DeviceType query.
 * Fixed client and four standard read-word registers; no command/configuration
 * writes, retries, polling threads, power-supply registration or charger setup.
 * Direct temperature omits the OEM's optional balancing compensation. Voltage
 * is the gauge's pack-voltage word, not the OEM's separately queried max cell.
 */
#include <linux/device.h>
#include <linux/errno.h>
#include <linux/i2c.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>

#define GAUGE_PATH "/i2c@11d04000/bq27541-battery@55"
#define ZY0603_TYPE 0xa5ff

static bool allow_reads;
static unsigned int confirmed_device_type;
module_param(allow_reads, bool, 0400);
module_param(confirmed_device_type, uint, 0400);
MODULE_PARM_DESC(allow_reads, "Explicitly allow fixed read-only observations");
MODULE_PARM_DESC(confirmed_device_type, "Previously observed same-boot DeviceType; must be 0xa5ff");

static struct device *sampled_device;
static DEFINE_MUTEX(sample_lock);

static ssize_t battery_snapshot_show(struct device *dev,
				     struct device_attribute *attr, char *buf)
{
	/* ZY0603 follows the BQ27541 map with current overridden to 0x0c. */
	static const u8 registers[] = { 0x06, 0x08, 0x0c, 0x2c };
	s32 words[4];
	int temperature = 0, gauge_current = 0;
	int temp_error, voltage_error, current_error, capacity_error;
	size_t i;

	if (dev != sampled_device)
		return -ENODATA;
	mutex_lock(&sample_lock);
	for (i = 0; i < ARRAY_SIZE(registers); i++)
		words[i] = i2c_smbus_read_word_data(to_i2c_client(dev), registers[i]);
	mutex_unlock(&sample_lock);

	temp_error = words[0] < 0 ? words[0] :
		(words[0] < 2331 || words[0] > 3981 ? -ERANGE : 0);
	voltage_error = words[1] < 0 ? words[1] : (words[1] == 0 || words[1] == 65535 ? -ERANGE : 0);
	current_error = words[2] < 0 ? words[2] : 0;
	capacity_error = words[3] < 0 ? words[3] : (words[3] > 100 ? -ERANGE : 0);
	if (!temp_error)
		temperature = (words[0] - 2731) * 100; /* stock OPLUS rounded offset */
	if (!current_error)
		gauge_current = words[2] & 0x8000 ? words[2] - 65536 : words[2];
	return scnprintf(buf, PAGE_SIZE,
		"gauge_device_type=%u\n"
		"temperature_raw=%d\ntemperature_millidegrees_celsius=%d\ntemperature_error=%d\n"
		"pack_voltage_mv=%d\nvoltage_error=%d\n"
		"gauge_current_ma_signed=%d\ncurrent_raw=%d\ncurrent_error=%d\n"
		"capacity_percent=%d\ncapacity_error=%d\n",
		confirmed_device_type, words[0], temperature, temp_error,
		words[1], voltage_error, gauge_current, words[2], current_error,
		words[3], capacity_error);
}
static DEVICE_ATTR_RO(battery_snapshot);
static struct attribute *battery_attrs[] = { &dev_attr_battery_snapshot.attr, NULL };
ATTRIBUTE_GROUPS(battery);

static int battery_probe(struct i2c_client *client)
{
	struct device_node *expected;
	bool matches;

	if (!allow_reads || confirmed_device_type != ZY0603_TYPE || sampled_device)
		return -EPERM;
	expected = of_find_node_by_path(GAUGE_PATH);
	matches = expected && client->dev.of_node == expected;
	of_node_put(expected);
	if (!matches || client->addr != 0x55 || client->adapter->nr != 7 ||
	    (client->flags & I2C_CLIENT_TEN) ||
	    !of_device_is_compatible(client->dev.of_node, "oplus,bq27541-battery") ||
	    !of_property_read_bool(client->dev.of_node, "qcom,batt_bq28z610"))
		return -ENODEV;
	sampled_device = &client->dev;
	dev_info(&client->dev, "LYNX_BATTERY_MONITOR_READY type=0xa5ff no_config_writes=1\n");
	return 0;
}

static const struct of_device_id battery_match[] = {
	{ .compatible = "oplus,bq27541-battery" }, { }
};
/* No aliases: this diagnostic must never autoload. */
static struct i2c_driver battery_driver = {
	.driver = { .name = "lynx-battery-monitor", .of_match_table = battery_match,
		    .dev_groups = battery_groups },
	.probe_new = battery_probe,
};
static int __init battery_init(void)
{
	if (!allow_reads || confirmed_device_type != ZY0603_TYPE)
		return -EPERM;
	return i2c_add_driver(&battery_driver);
}
static void __exit battery_exit(void)
{
	i2c_del_driver(&battery_driver);
	sampled_device = NULL;
}
module_init(battery_init);
module_exit(battery_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Lynx ZY0603 read-only battery snapshots; no charger control");
